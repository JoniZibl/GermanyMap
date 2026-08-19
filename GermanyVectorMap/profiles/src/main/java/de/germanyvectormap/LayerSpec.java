package de.germanyvectormap;

import java.util.Map;
import java.util.Set;

/**
 * Pre-computed, immutable settings for one output layer, built once at startup from
 * {@code config/layers.yml} + {@code config/zoom_levels.yml}.
 *
 * @param name                   layer name as it appears in the vector tile
 * @param enabled                {@code false} removes the layer from the output entirely
 * @param minZoom                first zoom the layer appears at
 * @param maxZoom                last zoom the layer appears at
 * @param minPixelSize           drop features smaller than this (below the max zoom)
 * @param minPixelSizeAtMaxZoom  same, at the deepest rendered zoom
 * @param bufferPixels           tile edge buffer
 * @param mergeLines             merge connected line strings per tile
 * @param mergeMinLength         drop merged lines shorter than this (px)
 * @param mergePolygons          union overlapping polygons per tile
 * @param mergeMinArea           drop merged polygons smaller than this (px^2)
 * @param mergeBelowZoom         only merge at zooms below this
 * @param nameMinZoom            first zoom the {@code name} attribute is written at
 * @param labelGridMaxZoom       apply a point label grid up to this zoom ({@code -1} = off)
 * @param labelGridSize          label grid cell size in px
 * @param labelGridLimit         max points kept per grid cell
 * @param classes                allow-list of {@code class} values, or {@code null} for "all"
 * @param raw                    the raw YAML mapping, for layer specific flags
 */
public record LayerSpec(
  String name,
  boolean enabled,
  int minZoom,
  int maxZoom,
  double minPixelSize,
  double minPixelSizeAtMaxZoom,
  double bufferPixels,
  boolean mergeLines,
  double mergeMinLength,
  boolean mergePolygons,
  double mergeMinArea,
  int mergeBelowZoom,
  int nameMinZoom,
  int labelGridMaxZoom,
  double labelGridSize,
  int labelGridLimit,
  Set<String> classes,
  Map<String, Object> raw
) {

  public static LayerSpec disabled(String name) {
    return new LayerSpec(name, false, 0, 0, 1, 0.5, 4, false, 0.5, false, 1, 0, 12, -1, 128, 4,
      null, Map.of());
  }

  /** True if this layer is enabled and accepts features of the given class. */
  public boolean accepts(String clazz) {
    return enabled && (classes == null || clazz == null || classes.contains(clazz));
  }

  public boolean flag(String key, boolean fallback) {
    return MapConfig.toBool(raw.get(key), fallback);
  }

  public int number(String key, int fallback) {
    return MapConfig.toInt(raw.get(key), fallback);
  }
}
