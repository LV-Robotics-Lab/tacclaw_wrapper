import math

import pytest

from tacclaw_wrapper import CollisionSphere, load_tool_collision_model


def test_checked_in_model_is_explicitly_estimated_and_unvalidated() -> None:
    model = load_tool_collision_model()
    assert model.frame == "tcp_link"
    assert model.measured_or_cad_validated is False
    assert "estimated" in model.geometry_source
    assert len(model.spheres) == 38


def test_checked_in_model_preserves_manual_profile_landmarks() -> None:
    model = load_tool_collision_model()
    lower = [
        tuple(center - sphere.radius_m for center in sphere.center_m)
        for sphere in model.spheres
    ]
    upper = [
        tuple(center + sphere.radius_m for center in sphere.center_m)
        for sphere in model.spheres
    ]
    assert min(value[1] for value in lower) <= -0.0885
    assert max(value[1] for value in upper) >= 0.0885
    assert min(value[0] for value in lower) <= -0.0622
    assert max(value[0] for value in upper) >= 0.0622
    assert min(value[2] for value in lower) <= -0.19448
    for sphere in model.spheres[:4]:
        assert sphere.radius_m == pytest.approx(0.009)
        assert sphere.center_m[2] - sphere.radius_m == pytest.approx(-0.19448)


def test_curobo_projection_preserves_sphere_values() -> None:
    model = load_tool_collision_model()
    projected = model.as_curobo_spheres()
    assert projected[0] == {
        "center": [-0.026, -0.01, -0.18548],
        "radius": 0.009,
    }


@pytest.mark.parametrize(
    ("center", "radius"),
    [
        ((0.0, 0.0), 0.1),
        ((0.0, 0.0, math.nan), 0.1),
        ((0.0, 0.0, 0.0), 0.0),
    ],
)
def test_collision_sphere_rejects_invalid_geometry(center, radius) -> None:
    with pytest.raises(ValueError):
        CollisionSphere(center, radius)
