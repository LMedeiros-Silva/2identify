from app.domain import NormalizedPoint, RiskAreaGeometry
from app.engine import RiskAreaPointRelation, RiskAreaSpatialEngine


def _geometry() -> RiskAreaGeometry:
    return RiskAreaGeometry(
        (
            NormalizedPoint(0.2, 0.2),
            NormalizedPoint(0.8, 0.2),
            NormalizedPoint(0.8, 0.8),
            NormalizedPoint(0.2, 0.8),
        )
    )


def test_spatial_engine_classifies_inside_boundary_and_outside() -> None:
    engine = RiskAreaSpatialEngine()
    geometry = _geometry()

    assert engine.classify_point(geometry, NormalizedPoint(0.5, 0.5)) is (
        RiskAreaPointRelation.INSIDE
    )
    assert engine.classify_point(geometry, NormalizedPoint(0.2, 0.5)) is (
        RiskAreaPointRelation.BOUNDARY
    )
    assert engine.classify_point(geometry, NormalizedPoint(0.1, 0.5)) is (
        RiskAreaPointRelation.OUTSIDE
    )


def test_spatial_engine_has_explicit_boundary_policy() -> None:
    engine = RiskAreaSpatialEngine()
    geometry = _geometry()
    boundary = NormalizedPoint(0.2, 0.5)

    assert engine.contains_point(geometry, boundary)
    assert not engine.contains_point(
        geometry,
        boundary,
        include_boundary=False,
    )
