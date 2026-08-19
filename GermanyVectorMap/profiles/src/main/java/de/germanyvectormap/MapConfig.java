package de.germanyvectormap;

import com.onthegomap.planetiler.FeatureCollector;
import com.onthegomap.planetiler.geo.SimplifyMethod;
import com.onthegomap.planetiler.util.ZoomFunction;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.snakeyaml.engine.v2.api.Load;
import org.snakeyaml.engine.v2.api.LoadSettings;

/**
 * Reads {@code config/layers.yml} and {@code config/zoom_levels.yml} and turns them into typed,
 * pre-computed {@link LayerSpec}s so that the hot path in {@link GermanyMapProfile} never touches a
 * map lookup chain.
 *
 * <p>Nothing in here knows about colors — the config controls geometry, zoom windows and
 * simplification only.
 */
public final class MapConfig {

  private final Map<String, Object> layersRoot;
  private final Map<String, Object> zoomRoot;
  private final Map<String, Object> defaults;
  private final Map<String, Object> layerCfg;
  private final Map<String, Object> zoomLayerCfg;
  private final Map<String, Object> featureRules;
  private final Map<String, Object> simplification;

  private final int tileMinZoom;
  private final int tileMaxZoom;
  private final int renderMaxZoom;
  private final boolean excludeIds;
  private final String tileCompression;

  private final SimplifyMethod simplifyMethod;
  private final double tolerance;
  private final double toleranceAtMaxZoom;
  private final double minFeatureSize;
  private final double minFeatureSizeAtMaxZoom;
  private final ZoomFunction<Number> toleranceByZoom;

  private final RoadLayerMode roadLayerMode;
  private final Map<String, LayerSpec> specs = new LinkedHashMap<>();

  public enum RoadLayerMode {
    SPLIT, SINGLE
  }

  private MapConfig(Map<String, Object> layersRoot, Map<String, Object> zoomRoot) {
    this.layersRoot = layersRoot;
    this.zoomRoot = zoomRoot;
    this.defaults = map(layersRoot, "defaults");
    this.layerCfg = map(layersRoot, "layers");
    this.zoomLayerCfg = map(zoomRoot, "layers");
    this.featureRules = map(zoomRoot, "features");
    this.simplification = map(zoomRoot, "simplification");

    Map<String, Object> tileset = map(zoomRoot, "tileset");
    this.tileMinZoom = toInt(tileset.get("min_zoom"), 0);
    this.tileMaxZoom = toInt(tileset.get("max_zoom"), 14);
    this.renderMaxZoom = toInt(tileset.get("render_max_zoom"), tileMaxZoom);
    this.excludeIds = toBool(tileset.get("exclude_feature_ids"), true);
    this.tileCompression = toStr(tileset.get("tile_compression"), "gzip");

    this.simplifyMethod =
      SimplifyMethod.valueOf(toStr(simplification.get("method"), "RETAIN_IMPORTANT_POINTS"));
    this.tolerance = toDouble(simplification.get("tolerance"), 0.375);
    this.toleranceAtMaxZoom = toDouble(simplification.get("tolerance_at_max_zoom"), 0.0625);
    this.minFeatureSize = toDouble(simplification.get("min_feature_size"), 1.0);
    this.minFeatureSizeAtMaxZoom = toDouble(simplification.get("min_feature_size_at_max_zoom"), 0.5);

    Map<Integer, Number> bands = new TreeMap<>();
    for (Object band : list(simplification, "bands")) {
      Map<String, Object> b = asMap(band);
      bands.put(toInt(b.get("max_zoom"), tileMaxZoom), toDouble(b.get("tolerance"), tolerance));
    }
    this.toleranceByZoom =
      bands.isEmpty() ? null : ZoomFunction.fromMaxZoomThresholds(bands, tolerance);

    this.roadLayerMode = "single".equalsIgnoreCase(toStr(layersRoot.get("road_layer_mode"), "split"))
      ? RoadLayerMode.SINGLE
      : RoadLayerMode.SPLIT;

    for (String name : layerCfg.keySet()) {
      specs.put(name, buildSpec(name));
    }
  }

  public static MapConfig load(Path layersYml, Path zoomYml) {
    return new MapConfig(readYaml(layersYml), readYaml(zoomYml));
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> readYaml(Path path) {
    LoadSettings settings = LoadSettings.builder().setLabel(path.toString()).build();
    try (InputStream in = Files.newInputStream(path)) {
      Object parsed = new Load(settings).loadFromInputStream(in);
      if (!(parsed instanceof Map)) {
        throw new IllegalArgumentException(path + ": expected a YAML mapping at the top level");
      }
      return (Map<String, Object>) parsed;
    } catch (java.io.IOException e) {
      throw new IllegalArgumentException("Cannot read " + path, e);
    }
  }

  // ---------------------------------------------------------------- accessors

  public int tileMinZoom() {
    return tileMinZoom;
  }

  public int tileMaxZoom() {
    return tileMaxZoom;
  }

  public int renderMaxZoom() {
    return renderMaxZoom;
  }

  public boolean excludeIds() {
    return excludeIds;
  }

  public String tileCompression() {
    return tileCompression;
  }

  /** Simplification tolerance (in tile pixels) that applies at the given zoom. */
  public double toleranceAtZoom(int zoom) {
    if (zoom >= renderMaxZoom) {
      return toleranceAtMaxZoom;
    }
    return toleranceByZoom == null ? tolerance
      : ZoomFunction.applyAsDoubleOrElse(toleranceByZoom, zoom, tolerance);
  }

  public double minFeatureSize() {
    return minFeatureSize;
  }

  public double minFeatureSizeAtMaxZoom() {
    return minFeatureSizeAtMaxZoom;
  }

  public RoadLayerMode roadLayerMode() {
    return roadLayerMode;
  }

  public Map<String, LayerSpec> specs() {
    return Collections.unmodifiableMap(specs);
  }

  /** Returns the spec for {@code name}, or a disabled placeholder if the layer is unknown. */
  public LayerSpec layer(String name) {
    LayerSpec spec = specs.get(name);
    return spec != null ? spec : LayerSpec.disabled(name);
  }

  public boolean enabled(String name) {
    return layer(name).enabled();
  }

  /**
   * Feature-level zoom rule, e.g. {@code featureZoom("boundary", "county", 8)} reads
   * {@code features.boundary.county} from zoom_levels.yml.
   */
  public int featureZoom(String group, String key, int fallback) {
    Object g = featureRules.get(group);
    if (g instanceof Map<?, ?> m) {
      return toInt(m.get(key), fallback);
    }
    return fallback;
  }

  /**
   * Population driven zoom rule for the {@code place_*} layers: walks the list of
   * {@code {min_population, zoom}} entries and returns the zoom of the first match.
   */
  public int placeZoom(String group, long population, int fallback) {
    Object g = featureRules.get(group);
    if (g instanceof List<?> entries) {
      for (Object entry : entries) {
        Map<String, Object> e = asMap(entry);
        long threshold = (long) toDouble(e.get("min_population"), 0);
        if (population >= threshold) {
          return toInt(e.get("zoom"), fallback);
        }
      }
    }
    return fallback;
  }

  // ------------------------------------------------------------ spec building

  private LayerSpec buildSpec(String name) {
    Map<String, Object> raw = map(layerCfg, name);
    Map<String, Object> zoom = map(zoomLayerCfg, name);

    int minZoom = toInt(zoom.get("min_zoom"), 0);
    int maxZoom = toInt(zoom.get("max_zoom"), tileMaxZoom);

    Set<String> classes = null;
    Object classList = raw.get("classes");
    if (classList instanceof List<?> l && !l.isEmpty()) {
      classes = new LinkedHashSet<>();
      for (Object o : l) {
        classes.add(String.valueOf(o));
      }
    }

    return new LayerSpec(
      name,
      toBool(pick(raw, "enabled"), true),
      minZoom,
      maxZoom,
      toDouble(pick(raw, "min_pixel_size"), 1.0),
      toDouble(pick(raw, "min_pixel_size_at_max_zoom"), 0.5),
      toDouble(pick(raw, "buffer_pixels"), 4.0),
      toBool(pick(raw, "merge_lines"), false),
      toDouble(pick(raw, "merge_min_length"), 0.5),
      toBool(pick(raw, "merge_polygons"), false),
      toDouble(pick(raw, "merge_min_area"), 1.0),
      toInt(pick(raw, "merge_below_zoom"), renderMaxZoom),
      toInt(pick(raw, "name_min_zoom"), 12),
      toInt(pick(raw, "label_grid_max_zoom"), -1),
      toDouble(pick(raw, "label_grid_size"), 128),
      toInt(pick(raw, "label_grid_limit"), 4),
      classes,
      raw);
  }

  /** Looks a key up in the layer config, falling back to {@code defaults:}. */
  private Object pick(Map<String, Object> raw, String key) {
    Object v = raw.get(key);
    return v != null ? v : defaults.get(key);
  }

  // ------------------------------------------------------------------ styling

  /**
   * Applies all geometry-level settings of a layer to a feature: zoom window, buffer, minimum
   * pixel size, simplification and (for points) the label grid.
   */
  public FeatureCollector.Feature apply(FeatureCollector.Feature feature, LayerSpec spec,
    int minZoom) {
    feature
      .setMinZoom(Math.max(minZoom, spec.minZoom()))
      .setMaxZoom(spec.maxZoom())
      .setBufferPixels(spec.bufferPixels())
      .setSimplifyMethod(simplifyMethod)
      .setPixelToleranceAtMaxZoom(toleranceAtMaxZoom);
    if (toleranceByZoom != null) {
      feature.setPixelToleranceOverrides(toleranceByZoom);
    } else {
      feature.setPixelTolerance(tolerance);
    }
    if (!feature.getGeometry().getGeometryType().equals("Point")) {
      feature.setMinPixelSize(spec.minPixelSize()).setMinPixelSizeAtMaxZoom(
        spec.minPixelSizeAtMaxZoom());
    }
    if (spec.labelGridMaxZoom() >= 0) {
      feature.setPointLabelGridSizeAndLimit(spec.labelGridMaxZoom(), spec.labelGridSize(),
        spec.labelGridLimit());
    }
    return feature;
  }

  // -------------------------------------------------------------- yaml helpers

  @SuppressWarnings("unchecked")
  static Map<String, Object> asMap(Object o) {
    return o instanceof Map ? (Map<String, Object>) o : Map.of();
  }

  static Map<String, Object> map(Map<String, Object> parent, String key) {
    return parent == null ? Map.of() : asMap(parent.get(key));
  }

  static List<Object> list(Map<String, Object> parent, String key) {
    Object o = parent == null ? null : parent.get(key);
    return o instanceof List<?> l ? new ArrayList<>(l) : List.of();
  }

  static int toInt(Object o, int fallback) {
    return (int) toDouble(o, fallback);
  }

  static double toDouble(Object o, double fallback) {
    if (o instanceof Number n) {
      return n.doubleValue();
    }
    if (o instanceof String s && !s.isBlank()) {
      try {
        return Double.parseDouble(s.trim());
      } catch (NumberFormatException ignored) {
        return fallback;
      }
    }
    return fallback;
  }

  static boolean toBool(Object o, boolean fallback) {
    if (o instanceof Boolean b) {
      return b;
    }
    if (o instanceof String s) {
      return "true".equalsIgnoreCase(s.trim()) || "yes".equalsIgnoreCase(s.trim());
    }
    return fallback;
  }

  static String toStr(Object o, String fallback) {
    return o == null ? fallback : String.valueOf(o);
  }

  Map<String, Object> layersRoot() {
    return layersRoot;
  }

  Map<String, Object> zoomRoot() {
    return zoomRoot;
  }
}
