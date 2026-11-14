from dataclasses import dataclass


@dataclass(frozen=True)
class ClimateLocation:
    id: str
    name: str
    district: str
    latitude: float
    longitude: float


LOCATIONS: dict[str, ClimateLocation] = {
    "pamplemousses-04": ClimateLocation("pamplemousses-04", "Pamplemousses Field 04", "Pamplemousses District", -20.103, 57.575),
    "flacq-02": ClimateLocation("flacq-02", "Flacq Field 02", "Flacq District", -20.189, 57.714),
    "black-river-01": ClimateLocation("black-river-01", "Black River Field 01", "Black River District", -20.375, 57.381),
}
