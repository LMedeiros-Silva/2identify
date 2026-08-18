import pytest

from app.domain import NormalizedPoint, RiskAreaGeometry


def _point(x: float, y: float) -> NormalizedPoint:
    return NormalizedPoint(x, y)


def test_risk_area_geometry_accepts_simple_normalized_polygon() -> None:
    geometry = RiskAreaGeometry(
        (
            _point(0.1, 0.2),
            _point(0.9, 0.2),
            _point(0.8, 0.9),
            _point(0.2, 0.9),
            _point(0.1, 0.2),
        )
    )

    assert len(geometry.vertices) == 4
    assert geometry.vertices[0] == _point(0.1, 0.2)


@pytest.mark.parametrize(
    ("x", "y"),
    [(-0.1, 0.5), (1.1, 0.5), (0.5, -0.1), (0.5, 1.1)],
)
def test_normalized_point_rejects_coordinates_outside_frame(
    x: float,
    y: float,
) -> None:
    with pytest.raises(ValueError, match="entre zero e um"):
        NormalizedPoint(x, y)


@pytest.mark.parametrize(
    "vertices",
    [
        (_point(0.1, 0.1), _point(0.9, 0.9)),
        (_point(0.1, 0.1), _point(0.5, 0.5), _point(0.9, 0.9)),
        (
            _point(0.1, 0.1),
            _point(0.9, 0.8),
            _point(0.2, 0.9),
            _point(0.8, 0.2),
        ),
    ],
)
def test_risk_area_geometry_rejects_invalid_polygons(
    vertices: tuple[NormalizedPoint, ...],
) -> None:
    with pytest.raises(ValueError):
        RiskAreaGeometry(vertices)
