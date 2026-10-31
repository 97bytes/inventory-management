"""
Tests for restocking API endpoints.
"""
from datetime import datetime

import pytest

from mock_data import restocking_orders


@pytest.fixture(autouse=True)
def clean_restocking_orders():
    """Submitted orders live in a shared in-memory list, so empty it around every test."""
    restocking_orders.clear()
    yield
    restocking_orders.clear()


class TestRestockRecommendationEndpoints:
    """Test suite for the restocking recommendation endpoint."""

    def test_zero_budget_recommends_nothing(self, client):
        """Test that a zero budget returns no items."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0
        assert data["lead_time_days"] == 0

    def test_recommendation_structure(self, client):
        """Test that recommendation items have the expected fields."""
        response = client.get("/api/restocking/recommendations?budget=50000")
        assert response.status_code == 200

        data = response.json()
        assert len(data["items"]) > 0
        for item in data["items"]:
            assert "item_sku" in item
            assert "item_name" in item
            assert "trend" in item
            assert "forecasted_demand" in item
            assert "quantity_on_hand" in item
            assert "recommended_quantity" in item
            assert "unit_cost" in item
            assert "line_total" in item
            assert "lead_time_days" in item
            assert "supplier" in item

    @pytest.mark.parametrize("budget", [1, 500, 12.75, 1000, 25000, 100000])
    def test_total_never_exceeds_budget(self, client, budget):
        """Test that the recommended total stays within the budget."""
        data = client.get(f"/api/restocking/recommendations?budget={budget}").json()

        assert data["total_cost"] <= budget
        assert abs(data["total_cost"] + data["remaining_budget"] - budget) < 0.01
        line_sum = sum(item["line_total"] for item in data["items"])
        assert abs(line_sum - data["total_cost"]) < 0.01

    def test_line_total_calculation(self, client):
        """Test that each line total is quantity times unit cost."""
        data = client.get("/api/restocking/recommendations?budget=50000").json()

        for item in data["items"]:
            assert abs(item["line_total"] - item["recommended_quantity"] * item["unit_cost"]) < 0.01

    def test_items_ranked_by_demand_growth(self, client):
        """Test that items come back in order of forecast growth, biggest first."""
        forecasts = {f["item_sku"]: f for f in client.get("/api/demand").json()}
        data = client.get("/api/restocking/recommendations?budget=1000000").json()

        growth = [
            forecasts[item["item_sku"]]["forecasted_demand"] - forecasts[item["item_sku"]]["current_demand"]
            for item in data["items"]
        ]
        assert growth == sorted(growth, reverse=True)
        # Largest growth, with the higher forecast breaking the tie
        assert [item["item_sku"] for item in data["items"][:2]] == ["FLT-405", "WDG-001"]

    def test_decreasing_and_covered_items_excluded(self, client):
        """Test that falling-demand items and items already in stock are not recommended."""
        data = client.get("/api/restocking/recommendations?budget=1000000").json()
        skus = [item["item_sku"] for item in data["items"]]

        # MTR-304 has a decreasing trend; PSU-501 on-hand stock already covers its forecast
        assert "MTR-304" not in skus
        assert "PSU-501" not in skus
        for item in data["items"]:
            assert item["trend"] != "decreasing"
            assert item["recommended_quantity"] <= item["forecasted_demand"] - item["quantity_on_hand"]

    def test_last_item_quantity_trimmed_to_budget(self, client):
        """Test that the quantity is cut down to what the remaining budget can buy."""
        # FLT-405 costs 26.00, so 1000 buys 38 units (988.00). Nothing else fits in the last 12.00.
        data = client.get("/api/restocking/recommendations?budget=1000").json()

        assert len(data["items"]) == 1
        assert data["items"][0]["item_sku"] == "FLT-405"
        assert data["items"][0]["recommended_quantity"] == 38
        assert data["remaining_budget"] == 12.0

    def test_unaffordable_item_skipped_not_blocking(self, client):
        """Test that an item that cannot afford one unit does not stop cheaper items."""
        # 12.75 cannot buy FLT-405 (26.00) or WDG-001 (48.50) but buys one GSK-203 (12.75)
        data = client.get("/api/restocking/recommendations?budget=12.75").json()

        assert [item["item_sku"] for item in data["items"]] == ["GSK-203"]
        assert data["items"][0]["recommended_quantity"] == 1
        assert data["remaining_budget"] == 0

    def test_larger_budget_never_recommends_fewer_units(self, client):
        """Test that raising the budget does not reduce the total units recommended."""
        def total_units(budget):
            items = client.get(f"/api/restocking/recommendations?budget={budget}").json()["items"]
            return sum(item["recommended_quantity"] for item in items)

        assert total_units(5000) <= total_units(20000) <= total_units(100000)

    def test_lead_time_is_slowest_item(self, client):
        """Test that the order lead time is the longest lead time among items."""
        data = client.get("/api/restocking/recommendations?budget=100000").json()

        assert data["lead_time_days"] == max(item["lead_time_days"] for item in data["items"])

    def test_negative_budget_rejected(self, client):
        """Test that a negative budget returns 400."""
        response = client.get("/api/restocking/recommendations?budget=-1")
        assert response.status_code == 400
        assert "detail" in response.json()

    @pytest.mark.parametrize("budget", ["nan", "inf", "-inf", "1e308", "10000001"])
    def test_non_finite_or_huge_budget_rejected(self, client, budget):
        """Test that nan, infinite and oversized budgets return 400 rather than crashing."""
        response = client.get(f"/api/restocking/recommendations?budget={budget}")
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_missing_budget_rejected(self, client):
        """Test that omitting the budget returns a validation error."""
        response = client.get("/api/restocking/recommendations")
        assert response.status_code == 422


class TestRestockOrderEndpoints:
    """Test suite for submitting and listing restocking orders."""

    ORDER = {
        "budget": 5000,
        "items": [
            {"item_sku": "FLT-405", "quantity": 10},
            {"item_sku": "WDG-001", "quantity": 5},
        ],
    }

    def test_create_order(self, client):
        """Test submitting an order."""
        response = client.post("/api/restocking/orders", json=self.ORDER)
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"] == "RST-0001"
        assert order["status"] == "Submitted"
        assert len(order["items"]) == 2
        # 10 x 26.00 + 5 x 48.50
        assert abs(order["total_cost"] - 502.5) < 0.01

    def test_order_prices_come_from_catalog(self, client):
        """Test that unit costs and lead times are filled in by the server."""
        order = client.post("/api/restocking/orders", json=self.ORDER).json()

        lines = {line["sku"]: line for line in order["items"]}
        assert lines["FLT-405"]["unit_cost"] == 26.0
        assert lines["FLT-405"]["lead_time_days"] == 5
        assert lines["WDG-001"]["unit_cost"] == 48.5
        assert lines["WDG-001"]["name"] == "Industrial Widget Type A"

    def test_order_lead_time_and_delivery_date(self, client):
        """Test that lead time is the slowest item and delivery is created date plus lead time."""
        order = client.post("/api/restocking/orders", json=self.ORDER).json()

        assert order["lead_time_days"] == 14
        created = datetime.fromisoformat(order["created_date"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        assert (expected - created).days == 14

    def test_order_over_budget_rejected(self, client):
        """Test that an order costing more than the budget returns 400."""
        payload = {"budget": 100, "items": self.ORDER["items"]}
        response = client.post("/api/restocking/orders", json=payload)

        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restocking/orders").json() == []

    def test_order_unknown_sku_rejected(self, client):
        """Test that an unknown SKU returns 400."""
        payload = {"budget": 5000, "items": [{"item_sku": "NOPE-999", "quantity": 1}]}
        response = client.post("/api/restocking/orders", json=payload)

        assert response.status_code == 400
        assert "NOPE-999" in response.json()["detail"]

    def test_order_empty_items_rejected(self, client):
        """Test that an order with no items returns 400."""
        response = client.post("/api/restocking/orders", json={"budget": 5000, "items": []})
        assert response.status_code == 400

    @pytest.mark.parametrize("quantity", [0, -3])
    def test_order_non_positive_quantity_rejected(self, client, quantity):
        """Test that a quantity below 1 returns 400."""
        payload = {"budget": 5000, "items": [{"item_sku": "FLT-405", "quantity": quantity}]}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400

    def test_order_duplicate_sku_rejected(self, client):
        """Test that the same SKU listed twice returns 400 and stores nothing."""
        payload = {
            "budget": 5000,
            "items": [
                {"item_sku": "FLT-405", "quantity": 1},
                {"item_sku": "FLT-405", "quantity": 2},
            ],
        }
        response = client.post("/api/restocking/orders", json=payload)

        assert response.status_code == 400
        assert client.get("/api/restocking/orders").json() == []

    def test_order_excessive_quantity_rejected(self, client):
        """Test that an unreasonably large quantity returns 400."""
        payload = {"budget": 10_000_000, "items": [{"item_sku": "FLT-405", "quantity": 1_000_000}]}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400

    @pytest.mark.parametrize("budget", ["NaN", "Infinity", "-1", "1e308"])
    def test_order_invalid_budget_rejected(self, client, budget):
        """Test that nan, infinite, negative and oversized budgets return 400 on submit."""
        # Raw body: the JSON encoder would refuse to serialize NaN/Infinity for us
        body = '{"budget": %s, "items": [{"item_sku": "FLT-405", "quantity": 1}]}' % budget
        response = client.post(
            "/api/restocking/orders", content=body, headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        assert client.get("/api/restocking/orders").json() == []

    def test_order_missing_fields_rejected(self, client):
        """Test that a malformed body returns a validation error."""
        response = client.post("/api/restocking/orders", json={"items": []})
        assert response.status_code == 422

    def test_get_orders_empty(self, client):
        """Test that no orders are listed before any are submitted."""
        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first."""
        first = client.post("/api/restocking/orders", json=self.ORDER).json()
        second = client.post("/api/restocking/orders", json=self.ORDER).json()

        listed = client.get("/api/restocking/orders").json()
        assert [o["order_number"] for o in listed] == [second["order_number"], first["order_number"]]

    def test_restocking_orders_separate_from_customer_orders(self, client):
        """Test that submitting a restocking order does not touch customer orders or the dashboard."""
        orders_before = len(client.get("/api/orders").json())
        summary_before = client.get("/api/dashboard/summary").json()

        client.post("/api/restocking/orders", json=self.ORDER)

        assert len(client.get("/api/orders").json()) == orders_before
        assert client.get("/api/dashboard/summary").json() == summary_before

    def test_recommendation_can_be_submitted(self, client):
        """Test that a recommendation returned for a budget can be placed as an order."""
        recommendation = client.get("/api/restocking/recommendations?budget=20000").json()
        payload = {
            "budget": 20000,
            "items": [
                {"item_sku": item["item_sku"], "quantity": item["recommended_quantity"]}
                for item in recommendation["items"]
            ],
        }

        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201
        order = response.json()
        assert abs(order["total_cost"] - recommendation["total_cost"]) < 0.01
        assert order["lead_time_days"] == recommendation["lead_time_days"]
