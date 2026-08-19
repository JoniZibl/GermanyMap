package de.germanyvectormap;

import com.onthegomap.planetiler.FeatureCollector;
import com.onthegomap.planetiler.FeatureMerge;
import com.onthegomap.planetiler.Profile;
import com.onthegomap.planetiler.VectorTile;
import com.onthegomap.planetiler.geo.GeometryException;
import com.onthegomap.planetiler.reader.SourceFeature;
import com.onthegomap.planetiler.reader.osm.OsmElement;
import com.onthegomap.planetiler.reader.osm.OsmReader;
import com.onthegomap.planetiler.reader.osm.OsmRelationInfo;
import com.onthegomap.planetiler.util.Parse;
import com.onthegomap.planetiler.util.ZoomFunction;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Germany Vector Map profile.
 *
 * <p>Turns raw OpenStreetMap data into a slim, clearly layered vector tile set. Everything that
 * would only ever be micro detail on a game/adventure style map (post boxes, waste baskets, power
 * towers, single trees, benches, street lamps, traffic signs, lane and speed limit info, fences,
 * house numbers, shops, restaurants, ...) is never emitted in the first place — the cheapest data
 * is the data you never write.
 *
 * <p>No colors are produced here. Every feature carries geometry, a {@code class} and, from the
 * configured zoom on, a {@code name}. Styling happens in {@code style/*.json} or in Figma.
 */
public class GermanyMapProfile implements Profile {

  private final MapConfig config;
  private final Map<String, LayerSpec> postProcessSpecs = new HashMap<>();

  // -- OSM tag sets, kept as static Sets so the hot path is a hash lookup ------

  private static final Set<String> WATER_NATURAL = Set.of("water", "glacier");
  private static final Set<String> WATER_LANDUSE = Set.of("reservoir", "basin");
  private static final Set<String> WATER_WATERWAY = Set.of("riverbank", "dock");
  private static final Set<String> WATER_EXCLUDE = Set.of("wastewater", "sewage");

  private static final Set<String> FOREST_LANDUSE = Set.of("forest");
  private static final Set<String> FOREST_NATURAL = Set.of("wood");

  private static final Set<String> PARK_LEISURE =
    Set.of("park", "nature_reserve", "recreation_ground", "common");
  private static final Set<String> PARK_BOUNDARY = Set.of("national_park", "protected_area");

  private static final Set<String> GARDEN_LEISURE = Set.of("garden");
  private static final Set<String> GARDEN_LANDUSE = Set.of("allotments", "orchard", "vineyard");

  private static final Set<String> GRASS_LANDUSE = Set.of("meadow", "grass", "village_green");
  private static final Set<String> GRASS_NATURAL = Set.of("grassland", "heath", "scrub");

  private static final Set<String> RAIL_SERVICE_IRRELEVANT =
    Set.of("yard", "siding", "spur", "crossover");
  private static final Set<String> RAIL_MAIN_USAGE = Set.of("main", "branch");

  private static final Set<String> POI_TOWER_KEEP =
    Set.of("observation", "bell_tower", "watchtower", "defensive", "clock", "campanile");
  private static final Set<String> POI_HISTORIC_KEEP =
    Set.of("manor", "monastery", "fort", "city_gate", "heritage", "aqueduct", "wayside_shrine",
      "church", "tower", "mansion", "castle_wall", "bunker", "pillory");

  private static final Set<String> BUILDING_KEEP_CLASS =
    Set.of("church", "chapel", "cathedral", "castle", "monastery", "train_station", "cityhall",
      "hospital", "school", "university", "stadium", "industrial", "commercial", "retail",
      "residential", "apartments", "house", "hotel");

  public GermanyMapProfile(MapConfig config) {
    this.config = config;
    postProcessSpecs.putAll(config.specs());
    if (config.roadLayerMode() == MapConfig.RoadLayerMode.SINGLE) {
      // in single-layer mode all roads land in one `road` layer; reuse the residential
      // merge settings for it (they are the most conservative of the road layers)
      postProcessSpecs.put("road", config.layer("road_residential"));
    }
  }

  // ---------------------------------------------------------------- metadata

  @Override
  public String name() {
    return "Germany Vector Map";
  }

  @Override
  public String description() {
    return "Slim, multi-zoom vector basemap of Germany built from OpenStreetMap data. "
      + "Geometry only — colors are applied by the style, not baked into the data.";
  }

  @Override
  public String attribution() {
    return Profile.OSM_ATTRIBUTION;
  }

  @Override
  public String version() {
    return "1.0";
  }

  @Override
  public Map<String, String> extraArchiveMetadata() {
    return Map.of(
      "license", "Open Database License (ODbL) 1.0",
      "license_url", "https://opendatacommons.org/licenses/odbl/1-0/",
      "source", "OpenStreetMap contributors",
      "producer", "GermanyVectorMap (Planetiler)");
  }

  // --------------------------------------------------------------- relations

  /** Admin level of a boundary relation, carried over to its member ways. */
  public record BoundaryRelation(long id, int adminLevel) implements OsmRelationInfo {}

  @Override
  public List<OsmRelationInfo> preprocessOsmRelation(OsmElement.Relation relation) {
    if (relation.hasTag("type", "boundary") && relation.hasTag("boundary", "administrative")) {
      Integer level = Parse.parseIntOrNull(relation.getString("admin_level"));
      if (level != null && (level == 2 || level == 4 || level == 6)) {
        return List.of(new BoundaryRelation(relation.id(), level));
      }
    }
    return null;
  }

  // ------------------------------------------------------------ main dispatch

  @Override
  public void processFeature(SourceFeature sf, FeatureCollector features) {
    processLand(sf, features);
    processBoundary(sf, features);
    processWater(sf, features);
    processWaterway(sf, features);
    processCoastline(sf, features);
    processNature(sf, features);
    processRoad(sf, features);
    processRail(sf, features);
    processBuilding(sf, features);
    processPlace(sf, features);
    processTransport(sf, features);
    processPoi(sf, features);
  }

  // ------------------------------------------------------------------- land

  /**
   * The Germany background area, taken from the OSM {@code admin_level=2} boundary relation (and,
   * optionally, the Bundesland relations). Only relations qualify — {@code type=boundary} exists
   * on relations only, so closed boundary ways cannot leak in here.
   */
  private void processLand(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("land");
    if (!spec.enabled() || !sf.canBePolygon()) {
      return;
    }
    if (!sf.hasTag("type", "boundary") || !sf.hasTag("boundary", "administrative")) {
      return;
    }
    Integer level = Parse.parseIntOrNull(sf.getString("admin_level"));
    if (level == null) {
      return;
    }
    String clazz;
    int minZoom;
    if (level == 2) {
      clazz = "country";
      minZoom = 0;
    } else if (level == 4 && spec.flag("include_states", true)) {
      clazz = "state";
      minZoom = config.featureZoom("boundary", "state", 4);
    } else {
      return;
    }
    FeatureCollector.Feature f = features.polygon("land");
    config.apply(f, spec, minZoom);
    f.setAttr("class", clazz);
    setName(f, sf, spec);
  }

  // --------------------------------------------------------------- boundary

  private void processBoundary(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("boundary");
    if (!spec.enabled() || sf.isPoint() || !sf.canBeLine()) {
      return;
    }
    if (!spec.flag("include_maritime", false) && sf.hasTag("maritime", "yes")) {
      return;
    }
    // the way itself may be tagged with a less significant level than the relation it belongs
    // to — take the most significant (lowest) admin_level of all relations it is part of
    int level = Integer.MAX_VALUE;
    for (OsmReader.RelationMember<BoundaryRelation> member : sf.relationInfo(
      BoundaryRelation.class)) {
      level = Math.min(level, member.relation().adminLevel());
    }
    if (level == Integer.MAX_VALUE && sf.hasTag("boundary", "administrative")) {
      Integer own = Parse.parseIntOrNull(sf.getString("admin_level"));
      if (own != null) {
        level = own;
      }
    }
    String clazz;
    int minZoom;
    if (level == 2) {
      clazz = "country";
      minZoom = config.featureZoom("boundary", "country", 0);
    } else if (level == 4) {
      clazz = "state";
      minZoom = config.featureZoom("boundary", "state", 4);
    } else if (level == 6 && spec.flag("include_counties", true)) {
      clazz = "county";
      minZoom = config.featureZoom("boundary", "county", 8);
    } else {
      return;
    }
    FeatureCollector.Feature f = features.line("boundary");
    config.apply(f, spec, minZoom);
    f.setAttr("class", clazz).setAttr("admin_level", level);
  }

  // ------------------------------------------------------------------ water

  private void processWater(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("water");
    if (!spec.enabled() || !sf.canBePolygon()) {
      return;
    }
    String natural = sf.getString("natural");
    String landuse = sf.getString("landuse");
    String waterway = sf.getString("waterway");
    String clazz = null;
    if (natural != null && WATER_NATURAL.contains(natural)) {
      String water = sf.getString("water");
      if (water != null && WATER_EXCLUDE.contains(water)) {
        return;
      }
      clazz = water != null ? water : "water";
    } else if (landuse != null && WATER_LANDUSE.contains(landuse)) {
      clazz = landuse;
    } else if (waterway != null && WATER_WATERWAY.contains(waterway)) {
      clazz = waterway;
    }
    if (clazz == null || !spec.accepts(clazz)) {
      return;
    }
    FeatureCollector.Feature f = features.polygon("water");
    config.apply(f, spec, spec.minZoom());
    f.setAttr("class", clazz);
    setName(f, sf, spec);
  }

  private void processWaterway(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("waterway");
    if (!spec.enabled() || sf.isPoint() || !sf.canBeLine() || sf.hasTag("area", "yes")) {
      return;
    }
    String waterway = sf.getString("waterway");
    if (waterway == null) {
      return;
    }
    int minZoom;
    switch (waterway) {
      case "river" -> minZoom = config.featureZoom("waterway", "river", 5);
      case "canal" -> minZoom = config.featureZoom("waterway", "canal", 10);
      case "stream" -> {
        if (!spec.flag("include_stream", true)) {
          return;
        }
        minZoom = config.featureZoom("waterway", "stream", 12);
      }
      case "ditch", "drain" -> {
        if (!spec.flag("include_ditch_drain", false)) {
          return;
        }
        minZoom = config.featureZoom("waterway", "ditch", 14);
      }
      default -> {
        return;
      }
    }
    if (!spec.accepts(waterway)) {
      return;
    }
    FeatureCollector.Feature f = features.line("waterway");
    config.apply(f, spec, minZoom);
    f.setAttr("class", waterway);
    setStructure(f, sf);
    setName(f, sf, spec);
  }

  private void processCoastline(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("coastline");
    if (!spec.enabled() || sf.isPoint() || !sf.canBeLine()
      || !sf.hasTag("natural", "coastline")) {
      return;
    }
    FeatureCollector.Feature f = features.line("coastline");
    config.apply(f, spec, spec.minZoom());
    f.setAttr("class", "coastline");
  }

  // ----------------------------------------------------------------- nature

  private void processNature(SourceFeature sf, FeatureCollector features) {
    if (!sf.canBePolygon()) {
      return;
    }
    String landuse = sf.getString("landuse");
    String natural = sf.getString("natural");
    String leisure = sf.getString("leisure");
    String boundary = sf.getString("boundary");

    LayerSpec forest = config.layer("forest");
    if (forest.enabled()
      && ((landuse != null && FOREST_LANDUSE.contains(landuse))
        || (natural != null && FOREST_NATURAL.contains(natural)))) {
      FeatureCollector.Feature f = features.polygon("forest");
      config.apply(f, forest, forest.minZoom());
      f.setAttr("class", natural != null && FOREST_NATURAL.contains(natural) ? "wood" : "forest");
      setName(f, sf, forest);
    }

    LayerSpec park = config.layer("park");
    if (park.enabled()) {
      String clazz = null;
      if (leisure != null && PARK_LEISURE.contains(leisure)) {
        clazz = leisure;
      } else if (boundary != null && PARK_BOUNDARY.contains(boundary)) {
        clazz = boundary;
      }
      if (clazz != null && park.accepts(clazz)) {
        FeatureCollector.Feature f = features.polygon("park");
        config.apply(f, park, park.minZoom());
        f.setAttr("class", clazz);
        setName(f, sf, park);
      }
    }

    LayerSpec garden = config.layer("garden");
    if (garden.enabled()) {
      String clazz = null;
      if (leisure != null && GARDEN_LEISURE.contains(leisure)) {
        clazz = leisure;
      } else if (landuse != null && GARDEN_LANDUSE.contains(landuse)) {
        clazz = landuse;
      }
      if (clazz != null && garden.accepts(clazz)) {
        FeatureCollector.Feature f = features.polygon("garden");
        config.apply(f, garden, garden.minZoom());
        f.setAttr("class", clazz);
        setName(f, sf, garden);
      }
    }

    LayerSpec grass = config.layer("grass");
    if (grass.enabled()) {
      String clazz = null;
      if (landuse != null && GRASS_LANDUSE.contains(landuse)) {
        clazz = landuse;
      } else if (natural != null && GRASS_NATURAL.contains(natural)) {
        clazz = natural;
      }
      if (clazz != null && grass.accepts(clazz)) {
        FeatureCollector.Feature f = features.polygon("grass");
        config.apply(f, grass, grass.minZoom());
        f.setAttr("class", clazz);
      }
    }
  }

  // ------------------------------------------------------------------ roads

  private void processRoad(SourceFeature sf, FeatureCollector features) {
    if (sf.isPoint() || !sf.canBeLine() || sf.hasTag("area", "yes")) {
      return;
    }
    String highway = sf.getString("highway");
    if (highway == null) {
      return;
    }
    String clazz;
    String layerKey;
    boolean link = highway.endsWith("_link");
    String base = link ? highway.substring(0, highway.length() - 5) : highway;

    switch (base) {
      case "motorway" -> {
        clazz = "motorway";
        layerKey = "road_motorway";
      }
      case "trunk" -> {
        clazz = "trunk";
        layerKey = "road_trunk";
      }
      case "primary" -> {
        clazz = "primary";
        layerKey = "road_primary";
      }
      case "secondary" -> {
        clazz = "secondary";
        layerKey = "road_secondary";
      }
      case "tertiary" -> {
        clazz = "tertiary";
        layerKey = "road_tertiary";
      }
      case "residential", "unclassified", "living_street" -> {
        clazz = base;
        layerKey = "road_residential";
      }
      case "service" -> {
        clazz = "service";
        layerKey = "road_service";
      }
      case "footway", "path", "pedestrian", "steps", "cycleway", "bridleway", "track" -> {
        processPath(sf, features, base);
        return;
      }
      default -> {
        return;
      }
    }

    LayerSpec spec = config.layer(layerKey);
    if (!spec.enabled() || !spec.accepts(clazz)) {
      return;
    }
    if ("service".equals(clazz)) {
      String service = sf.getString("service");
      if ("driveway".equals(service) && !spec.flag("include_driveways", false)) {
        return;
      }
      if ("parking_aisle".equals(service) && !spec.flag("include_parking_aisles", false)) {
        return;
      }
    }

    String outLayer =
      config.roadLayerMode() == MapConfig.RoadLayerMode.SINGLE ? "road" : layerKey;
    FeatureCollector.Feature f = features.line(outLayer);
    config.apply(f, spec, spec.minZoom());
    f.setAttr("class", clazz).setSortKey(sf.getWayZorder());
    if (link) {
      f.setAttr("link", 1);
    }
    setStructure(f, sf);
    setName(f, sf, spec);
    int refMinZoom = spec.number("ref_min_zoom", -1);
    String ref = sf.getString("ref");
    if (refMinZoom >= 0 && ref != null && ref.length() <= 12) {
      f.setAttr("ref", ZoomFunction.minZoom(refMinZoom, ref));
    }
  }

  private void processPath(SourceFeature sf, FeatureCollector features, String kind) {
    LayerSpec spec = config.layer("path");
    if (!spec.enabled() || !spec.accepts(kind)) {
      return;
    }
    int minZoom = config.featureZoom("path", kind, spec.minZoom());
    String outLayer = config.roadLayerMode() == MapConfig.RoadLayerMode.SINGLE ? "road" : "path";
    FeatureCollector.Feature f = features.line(outLayer);
    config.apply(f, spec, minZoom);
    f.setAttr("class", "path".equals(kind) ? "footway" : kind).setSortKey(sf.getWayZorder());
    setStructure(f, sf);
    setName(f, sf, spec);
  }

  private void processRail(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("rail");
    if (!spec.enabled() || sf.isPoint() || !sf.canBeLine()) {
      return;
    }
    String railway = sf.getString("railway");
    if (railway == null || !spec.accepts(railway)) {
      return;
    }
    String service = sf.getString("service");
    int minZoom;
    if (service != null && RAIL_SERVICE_IRRELEVANT.contains(service)) {
      if (!spec.flag("include_service_tracks", false)) {
        return;
      }
      minZoom = config.featureZoom("rail", "service", 13);
    } else {
      String usage = sf.getString("usage");
      minZoom = usage != null && RAIL_MAIN_USAGE.contains(usage)
        ? config.featureZoom("rail", "main", 8)
        : config.featureZoom("rail", "other", 11);
    }
    FeatureCollector.Feature f = features.line("rail");
    config.apply(f, spec, minZoom);
    f.setAttr("class", railway).setSortKey(sf.getWayZorder());
    setStructure(f, sf);
    setName(f, sf, spec);
  }

  // -------------------------------------------------------------- buildings

  private void processBuilding(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("building");
    if (!spec.enabled() || !sf.canBePolygon()) {
      return;
    }
    String building = sf.getString("building");
    if (building == null || "no".equals(building)) {
      return;
    }
    FeatureCollector.Feature f = features.polygon("building");
    config.apply(f, spec, spec.minZoom());
    if (spec.flag("keep_class", false) && BUILDING_KEEP_CLASS.contains(building)) {
      f.setAttr("class", building);
    }
  }

  // ----------------------------------------------------------------- places

  private void processPlace(SourceFeature sf, FeatureCollector features) {
    // places are taken from nodes only — the matching admin relations would duplicate them
    if (!sf.isPoint()) {
      return;
    }
    String place = sf.getString("place");
    if (place == null) {
      return;
    }
    String layerKey;
    String group;
    switch (place) {
      case "city" -> {
        layerKey = "place_city";
        group = "place_city";
      }
      case "town" -> {
        layerKey = "place_town";
        group = "place_town";
      }
      case "village" -> {
        layerKey = "place_village";
        group = "place_village";
      }
      case "hamlet", "isolated_dwelling" -> {
        layerKey = "place_village";
        group = "place_hamlet";
      }
      case "suburb", "quarter", "borough", "neighbourhood" -> {
        layerKey = "place_suburb";
        group = "place_suburb";
      }
      default -> {
        return;
      }
    }
    LayerSpec spec = config.layer(layerKey);
    if (!spec.enabled() || !spec.accepts(place)) {
      return;
    }
    if (("hamlet".equals(place) || "isolated_dwelling".equals(place))
      && !spec.flag("include_hamlets", true)) {
      return;
    }
    String name = sf.getString("name");
    if (name == null || name.isBlank()) {
      return;
    }
    long population = population(sf);
    int minZoom = config.placeZoom(group, population, spec.minZoom());

    FeatureCollector.Feature f = features.point(layerKey);
    config.apply(f, spec, minZoom);
    f.setAttr("class", place)
      .setAttr("name", name)
      .setSortKeyDescending((int) Math.min(population / 10, 1_000_000));
    if (population > 0) {
      f.setAttr("population", population);
    }
    Integer capital = Parse.parseIntOrNull(sf.getString("capital"));
    if (capital != null && (capital == 2 || capital == 4)) {
      f.setAttr("capital", capital);
    }
  }

  private static long population(SourceFeature sf) {
    Long parsed = Parse.parseLongOrNull(sf.getString("population"));
    return parsed == null || parsed < 0 ? 0 : parsed;
  }

  // -------------------------------------------------------------- transport

  private void processTransport(SourceFeature sf, FeatureCollector features) {
    LayerSpec spec = config.layer("transport");
    if (!spec.enabled()) {
      return;
    }
    String clazz = null;
    int minZoom = spec.minZoom();
    String railway = sf.getString("railway");
    String aeroway = sf.getString("aeroway");
    if ("station".equals(railway) || "halt".equals(railway)) {
      clazz = railway;
      minZoom = config.featureZoom("transport", railway, spec.minZoom());
    } else if ("aerodrome".equals(aeroway)) {
      clazz = "airport";
      boolean major = sf.hasTag("iata") || sf.hasTag("aerodrome:type", "international")
        || sf.hasTag("aerodrome", "international");
      minZoom = major ? config.featureZoom("transport", "airport", 9) : spec.minZoom() + 2;
    }
    if (clazz == null || !spec.accepts(clazz)) {
      return;
    }
    FeatureCollector.Feature f = sf.isPoint()
      ? features.point("transport")
      : features.pointOnSurface("transport");
    config.apply(f, spec, minZoom);
    f.setAttr("class", clazz);
    String name = sf.getString("name");
    if (name != null && !name.isBlank()) {
      f.setAttr("name", name);
    }
    String iata = sf.getString("iata");
    if (iata != null && iata.length() <= 4) {
      f.setAttr("ref", iata);
    }
  }

  // ------------------------------------------------------------------- POIs
  // Kept strictly separate from the base map layers so they can be toggled and
  // styled on their own.

  private void processPoi(SourceFeature sf, FeatureCollector features) {
    String historic = sf.getString("historic");
    String tourism = sf.getString("tourism");
    String amenity = sf.getString("amenity");
    String manMade = sf.getString("man_made");
    String building = sf.getString("building");

    // castles, palaces, fortresses
    if (historic != null || building != null) {
      String clazz = null;
      if ("castle".equals(historic)) {
        String type = sf.getString("castle_type");
        clazz = type != null && !type.isBlank() ? type : "castle";
      } else if ("palace".equals(historic)) {
        clazz = "palace";
      } else if ("fort".equals(historic)) {
        clazz = "fortress";
      } else if ("castle".equals(building) && historic == null) {
        clazz = "castle";
      }
      if (clazz != null) {
        emitPoi(sf, features, "poi_castle", clazz);
      }
    }

    // churches, chapels and other places of worship
    if ("place_of_worship".equals(amenity)
      || (building != null
        && (building.equals("church") || building.equals("chapel") || building.equals("cathedral")
          || building.equals("monastery")))) {
      String religion = sf.getString("religion");
      String clazz = religion != null && !religion.isBlank() ? religion
        : (building != null ? building : "place_of_worship");
      LayerSpec spec = config.layer("poi_church");
      if (!spec.flag("require_name", false) || sf.hasTag("name")) {
        emitPoi(sf, features, "poi_church", clazz);
      }
    }

    // ruins and archaeological sites
    if ("ruins".equals(historic) || "archaeological_site".equals(historic)
      || sf.hasTag("ruins", "yes")) {
      emitPoi(sf, features, "poi_ruin", historic != null ? historic : "ruins");
    }

    // monuments and memorials
    if ("monument".equals(historic) || "memorial".equals(historic) || "obelisk".equals(manMade)) {
      emitPoi(sf, features, "poi_monument", historic != null ? historic : "obelisk");
    }

    if ("viewpoint".equals(tourism)) {
      emitPoi(sf, features, "poi_viewpoint", "viewpoint");
    }

    if ("museum".equals(tourism)) {
      emitPoi(sf, features, "poi_museum", "museum");
    }

    // towers — landmark towers only, never communication/lighting/monitoring masts
    if ("tower".equals(manMade) || "lighthouse".equals(manMade) || "tower".equals(historic)) {
      String clazz = null;
      if ("lighthouse".equals(manMade)) {
        clazz = "lighthouse";
      } else {
        String type = sf.getString("tower:type");
        if ("tower".equals(historic) && (type == null || POI_TOWER_KEEP.contains(type))) {
          clazz = "historic";
        } else if (type != null && POI_TOWER_KEEP.contains(type)) {
          clazz = type;
        }
      }
      if (clazz != null) {
        emitPoi(sf, features, "poi_tower", clazz);
      }
    }

    // remaining historic buildings worth showing
    if (historic != null && POI_HISTORIC_KEEP.contains(historic)) {
      emitPoi(sf, features, "poi_historic", historic);
    }
  }

  private void emitPoi(SourceFeature sf, FeatureCollector features, String layer, String clazz) {
    LayerSpec spec = config.layer(layer);
    if (!spec.enabled() || !spec.accepts(clazz)) {
      return;
    }
    if (!sf.isPoint() && !sf.canBePolygon()) {
      return;
    }
    int minZoom = config.featureZoom("poi", layer, spec.minZoom());
    FeatureCollector.Feature f =
      sf.isPoint() ? features.point(layer) : features.pointOnSurface(layer);
    config.apply(f, spec, minZoom);
    f.setAttr("class", clazz);
    String name = sf.getString("name");
    if (name != null && !name.isBlank()) {
      f.setAttr("name", name);
      f.setSortKey(0); // named POIs win when the label grid thins points out
    } else {
      f.setSortKey(1);
    }
  }

  // -------------------------------------------------------------- utilities

  /** Writes the {@code name} attribute, but only from the layer's {@code name_min_zoom} on. */
  private void setName(FeatureCollector.Feature f, SourceFeature sf, LayerSpec spec) {
    String name = sf.getString("name");
    if (name == null || name.isBlank()) {
      return;
    }
    int minZoom = spec.nameMinZoom();
    f.setAttr("name", minZoom <= 0 ? name : ZoomFunction.minZoom(minZoom, name));
  }

  /** Bridge/tunnel as a single {@code structure} attribute — useful for styling, cheap to store. */
  private void setStructure(FeatureCollector.Feature f, SourceFeature sf) {
    if (sf.hasTag("bridge") && !sf.hasTag("bridge", "no")) {
      f.setAttr("structure", ZoomFunction.minZoom(12, "bridge"));
    } else if (sf.hasTag("tunnel") && !sf.hasTag("tunnel", "no")) {
      f.setAttr("structure", ZoomFunction.minZoom(12, "tunnel"));
    }
  }

  // --------------------------------------------------------- post processing

  @Override
  public List<VectorTile.Feature> postProcessLayerFeatures(String layer, int zoom,
    List<VectorTile.Feature> items) throws GeometryException {
    LayerSpec spec = postProcessSpecs.get(layer);
    if (spec == null || zoom >= spec.mergeBelowZoom()) {
      return items;
    }
    if (spec.mergeLines()) {
      return FeatureMerge.mergeLineStrings(items, spec.mergeMinLength(),
        config.toleranceAtZoom(zoom), (int) spec.bufferPixels());
    }
    if (spec.mergePolygons()) {
      return FeatureMerge.mergeOverlappingPolygons(items, spec.mergeMinArea());
    }
    return items;
  }
}
