package de.germanyvectormap;

import com.onthegomap.planetiler.Planetiler;
import com.onthegomap.planetiler.config.Arguments;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Entry point of the Germany Vector Map build.
 *
 * <pre>
 * java -cp planetiler.jar:germany-map-profile.jar de.germanyvectormap.GermanyMapMain \
 *      --input=input/germany-latest.osm.pbf \
 *      --output=output/germany_game_map.mbtiles \
 *      --layers-config=config/layers.yml \
 *      --zoom-config=config/zoom_levels.yml
 * </pre>
 *
 * <p>All standard Planetiler arguments still work and always win over the YAML defaults, so e.g.
 * {@code --maxzoom=15} or {@code --bounds=6.7,50.8,7.2,51.1} can be passed ad hoc.
 */
public class GermanyMapMain {

  public static void main(String[] args) throws Exception {
    Arguments cli = Arguments.fromArgsOrConfigFile(args);

    Path layersYml = cli.file("layers-config", "layer configuration", Path.of("config/layers.yml"));
    Path zoomYml =
      cli.file("zoom-config", "zoom level configuration", Path.of("config/zoom_levels.yml"));
    require(layersYml);
    require(zoomYml);

    MapConfig config = MapConfig.load(layersYml, zoomYml);

    // YAML values become *defaults*; anything passed on the command line overrides them.
    Map<String, String> defaults = new LinkedHashMap<>();
    defaults.put("minzoom", Integer.toString(config.tileMinZoom()));
    defaults.put("maxzoom", Integer.toString(config.tileMaxZoom()));
    defaults.put("render_maxzoom", Integer.toString(config.renderMaxZoom()));
    defaults.put("tile_compression", config.tileCompression());
    defaults.put("exclude_ids", Boolean.toString(config.excludeIds()));
    defaults.put("min_feature_size", Double.toString(config.minFeatureSize()));
    defaults.put("min_feature_size_at_max_zoom", Double.toString(config.minFeatureSizeAtMaxZoom()));
    // we never read Natural Earth / water polygon shapefiles — this build is OSM only
    defaults.put("download", "false");

    Arguments arguments = cli.orElse(Arguments.of(defaults));

    Path input = arguments.inputFile("input", "OSM .osm.pbf file to read",
      Path.of("input", "germany-latest.osm.pbf"));
    Path output = arguments.file("output", "output tile archive (.mbtiles or .pmtiles)",
      Path.of("output", "germany_game_map.mbtiles"));

    Files.createDirectories(output.toAbsolutePath().getParent());

    Planetiler.create(arguments)
      .setProfile(new GermanyMapProfile(config))
      .addOsmSource("osm", input)
      .overwriteOutput(output)
      .run();
  }

  private static void require(Path path) {
    if (!Files.isRegularFile(path)) {
      throw new IllegalArgumentException("Config file not found: " + path.toAbsolutePath());
    }
  }
}
