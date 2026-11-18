"""Standalone Folium map for a trip, generated server-side after prediction.

Each continuous stretch is drawn as its own Folium PolyLine; GPS gaps are
left open exactly as in the frontend map.
"""
import folium
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ..pipeline import service

router = APIRouter(tags=["visualization"])


@router.get("/trips/{trip_id}/map", response_class=HTMLResponse)
def folium_map(trip_id: str) -> HTMLResponse:
    run = service.get_run(trip_id)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail=f"No prediction has been run for {trip_id!r} yet. POST /api/match first.",
        )
    pipeline = service.get_pipeline()
    trip = run["trip"]

    lats = [ob["lat"] for ob in trip.observations]
    lons = [ob["lon"] for ob in trip.observations]
    center = [sum(lats) / len(lats), sum(lons) / len(lons)]
    fmap = folium.Map(location=center, zoom_start=15, tiles="OpenStreetMap")
    title = f"PathSnap - {trip_id}" + (" [MOCK DATA]" if pipeline.is_mock else "")
    fmap.get_root().html.add_child(folium.Element(f"<h3 style='font-family:sans-serif'>{title}</h3>"))

    gps_layer = folium.FeatureGroup(name="GPS observations")
    for ob in trip.observations:
        folium.CircleMarker(
            location=[ob["lat"], ob["lon"]],
            radius=4,
            color="#d62728",
            fill=True,
            fill_opacity=0.8,
            tooltip=f"obs {ob['index']} @ {ob['timestamp']}",
        ).add_to(gps_layer)
    gps_layer.add_to(fmap)

    route_layer = folium.FeatureGroup(name="Predicted route stretches")
    for st in run["stretches"]:
        folium.PolyLine(
            locations=st["geometry"],
            color="#1f77b4",
            weight=6,
            opacity=0.85,
            tooltip=(
                f"stretch {st['stretch_id']}: obs {st['from_obs']}-{st['to_obs']}, "
                f"arcs {len(st['arc_ids'])}"
                + (f" (incl. {len(st['reconstructed_arc_ids'])} reconstructed)" if st["reconstructed_arc_ids"] else "")
            ),
        ).add_to(route_layer)
    route_layer.add_to(fmap)

    for gap in run["gaps"]:
        folium.Marker(
            location=[
                trip.observations[gap["after_obs"]]["lat"] if gap["after_obs"] < len(trip.observations) else center[0],
                trip.observations[gap["after_obs"]]["lon"] if gap["after_obs"] < len(trip.observations) else center[1],
            ],
            icon=folium.Icon(color="orange", icon="exclamation-sign"),
            tooltip=f"GPS gap between obs {gap['after_obs']} and {gap['before_obs']}",
        ).add_to(fmap)

    folium.LayerControl().add_to(fmap)
    return HTMLResponse(fmap.get_root().render())
