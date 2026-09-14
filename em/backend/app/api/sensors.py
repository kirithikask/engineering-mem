from typing import Optional

from fastapi import APIRouter

from backend.app.services.sensor_service import sensor_service

router = APIRouter(prefix="/api/sensors", tags=["Condition Analysis"])


@router.get("/{machine_id}")
def get_condition_analysis(
    machine_id: str,
    oil_temp: Optional[float] = None,
    pressure: Optional[float] = None,
):
    """
    Hydraulic condition analysis for the supplied measurements.

    This endpoint deliberately does NOT synthesise telemetry. The platform has no
    live connection to any machine, so it reports:

      * the classifier's assessment of the measurements actually provided, and
      * measured aggregate statistics of the published hydraulic test-rig dataset
        the classifier was trained on.

    Anything resembling a live sensor trace would be fabricated, so none is
    returned. Callers are told explicitly that this is not machine telemetry.
    """
    inputs = {}
    if oil_temp is not None:
        inputs["oil_temperature"] = oil_temp
    if pressure is not None:
        inputs["pressure_bar"] = pressure

    # Without measurements there is nothing to assess: the classifier runs on the
    # default baseline and the response says so rather than inventing values.
    analysis = sensor_service.analyze_sensor_data(machine_id, inputs)
    analysis["measurements_supplied"] = bool(inputs)
    if not inputs:
        analysis["note"] = (
            "No measurements were supplied, so the assessment reflects baseline "
            "conditions only. Enter observed oil temperature and pressure for an "
            "assessment of this machine."
        )

    return {
        "machine_id": machine_id,
        "analysis": analysis,
        "reference_profile": sensor_service.reference_profile(),
        "reference_statistics": sensor_service.sensor_statistics(),
        "provenance": {
            "source": "UCI hydraulic condition monitoring dataset (test rig)",
            "is_machine_telemetry": False,
            "statement": (
                "Hydraulic test-rig condition-monitoring data. This is supporting "
                "evidence for condition classification, not live excavator telemetry."
            ),
        },
    }
