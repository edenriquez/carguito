from decimal import Decimal

from carguito.domain.services.forecasting import ForecastingService, SimulationInput


def test_projection_length_and_growth():
    sim = SimulationInput(
        starting_net_worth=Decimal("1000"),
        monthly_income=Decimal("5000"),
        monthly_expenses=Decimal("3000"),
        months=12,
    )
    points = ForecastingService().project(sim)
    assert len(points) == 12
    # With positive cash flow net worth strictly increases.
    assert points[-1].baseline_net_worth > points[0].baseline_net_worth


def test_optimized_beats_baseline_with_higher_savings():
    sim = SimulationInput(
        starting_net_worth=Decimal("0"),
        monthly_income=Decimal("5000"),
        monthly_expenses=Decimal("4000"),
        monthly_savings_override=Decimal("2000"),
        months=6,
    )
    points = ForecastingService().project(sim)
    assert points[-1].optimized_net_worth > points[-1].baseline_net_worth
