"""Validate cron and proactive behavior configurations.

Tests cover:
  - heartbeat.yaml structure and required fields
  - morning-briefing.yaml structure
  - standing-orders.yaml structure
  - CRON.md workspace file (if present)
"""

from pathlib import Path

import yaml
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CRON_DIR = PROJECT_ROOT / "platform" / "cron"


def _load_cron_yaml(filename: str) -> dict:
    """Load a YAML file from the cron directory."""
    path = CRON_DIR / filename
    assert path.exists(), f"platform/cron/{filename} not found"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{filename} did not parse to a dict"
    return data


# =========================================================================
# Heartbeat tests
# =========================================================================


class TestHeartbeat:
    """Test the heartbeat cron configuration."""

    @pytest.fixture
    def heartbeat(self):
        return _load_cron_yaml("heartbeat.yaml")

    def test_heartbeat_config_is_valid(self, heartbeat):
        """heartbeat.yaml must parse and have a 'heartbeat' key."""
        assert "heartbeat" in heartbeat, "Missing top-level 'heartbeat' key"

    def test_heartbeat_has_interval(self, heartbeat):
        """Heartbeat must define a default interval."""
        hb = heartbeat["heartbeat"]
        assert "default_interval" in hb, "Missing default_interval"

    def test_heartbeat_has_business_hours(self, heartbeat):
        """Heartbeat should respect business hours."""
        hb = heartbeat["heartbeat"]
        assert "business_hours" in hb, "Missing business_hours"
        bh = hb["business_hours"]
        assert "start" in bh, "Missing business_hours.start"
        assert "end" in bh, "Missing business_hours.end"

    def test_heartbeat_has_checks(self, heartbeat):
        """Heartbeat must define checks to run on each tick."""
        hb = heartbeat["heartbeat"]
        checks = hb.get("checks", [])
        assert len(checks) >= 2, (
            f"Expected at least 2 heartbeat checks, found {len(checks)}"
        )
        for check in checks:
            assert "id" in check, f"Check missing 'id': {check}"
            assert "description" in check, f"Check missing 'description': {check}"

    def test_heartbeat_has_dedup_rules(self, heartbeat):
        """Heartbeat should have anti-spam dedup rules."""
        hb = heartbeat["heartbeat"]
        dedup = hb.get("dedup", [])
        assert len(dedup) >= 1, "Heartbeat should have dedup rules"


# =========================================================================
# Morning briefing tests
# =========================================================================


class TestMorningBriefing:
    """Test the morning briefing cron configuration."""

    @pytest.fixture
    def briefing(self):
        return _load_cron_yaml("morning-briefing.yaml")

    def test_morning_briefing_config_is_valid(self, briefing):
        """morning-briefing.yaml must parse and have a 'morning_briefing' key."""
        assert "morning_briefing" in briefing, "Missing top-level 'morning_briefing' key"

    def test_morning_briefing_has_trigger(self, briefing):
        """Morning briefing must define how it's triggered."""
        mb = briefing["morning_briefing"]
        assert "trigger" in mb, "Missing trigger configuration"
        triggers = mb["trigger"]
        assert len(triggers) >= 1, "Must have at least one trigger"

    def test_morning_briefing_has_sections(self, briefing):
        """Morning briefing should define structured sections."""
        mb = briefing["morning_briefing"]
        sections = mb.get("sections", [])
        assert len(sections) >= 4, (
            f"Expected at least 4 briefing sections, found {len(sections)}"
        )
        for section in sections:
            assert "id" in section, f"Section missing 'id': {section}"
            assert "title" in section, f"Section missing 'title': {section}"

    def test_morning_briefing_has_cooldown(self, briefing):
        """Morning briefing should have a cooldown to prevent firing twice."""
        mb = briefing["morning_briefing"]
        assert "cooldown" in mb, "Missing cooldown configuration"

    def test_morning_briefing_blocked_items_first(self, briefing):
        """Blocked items should be the highest priority section."""
        mb = briefing["morning_briefing"]
        sections = mb.get("sections", [])
        priorities = {s["id"]: s.get("priority", 999) for s in sections}
        if "blocked_items" in priorities:
            assert priorities["blocked_items"] == 1, (
                "blocked_items should be priority 1"
            )


# =========================================================================
# Standing orders tests
# =========================================================================


class TestStandingOrders:
    """Test the standing orders configuration."""

    @pytest.fixture
    def standing(self):
        return _load_cron_yaml("standing-orders.yaml")

    def test_standing_orders_config_is_valid(self, standing):
        """standing-orders.yaml must parse and have a 'standing_orders' key."""
        assert "standing_orders" in standing, "Missing top-level 'standing_orders' key"

    def test_standing_orders_has_entries(self, standing):
        """Must have multiple standing orders defined."""
        orders = standing["standing_orders"]
        assert len(orders) >= 3, (
            f"Expected at least 3 standing orders, found {len(orders)}"
        )

    def test_standing_orders_have_structure(self, standing):
        """Each standing order must have id, description, trigger, and behavior."""
        orders = standing["standing_orders"]
        for order in orders:
            assert "id" in order, f"Order missing 'id': {order}"
            assert "description" in order, (
                f"Order '{order.get('id', '?')}' missing 'description'"
            )
            assert "trigger" in order, (
                f"Order '{order.get('id', '?')}' missing 'trigger'"
            )
            assert "behavior" in order, (
                f"Order '{order.get('id', '?')}' missing 'behavior'"
            )

    def test_sop_detection_standing_order_exists(self, standing):
        """SOP detection must be one of the standing orders."""
        orders = standing["standing_orders"]
        ids = [o["id"] for o in orders]
        assert "sop_detection" in ids, (
            f"sop_detection not found in standing orders: {ids}"
        )

    def test_health_check_standing_order_exists(self, standing):
        """Health check must be one of the standing orders."""
        orders = standing["standing_orders"]
        ids = [o["id"] for o in orders]
        assert "health_check" in ids, (
            f"health_check not found in standing orders: {ids}"
        )


# =========================================================================
# Cron directory tests
# =========================================================================


class TestCronDirectory:
    """Test the cron directory structure."""

    def test_cron_directory_exists(self):
        """platform/cron/ must exist."""
        assert CRON_DIR.is_dir(), "platform/cron/ directory not found"

    def test_all_cron_files_are_valid_yaml(self):
        """Every .yaml file in cron/ must parse."""
        for yaml_file in CRON_DIR.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                assert isinstance(data, dict), (
                    f"{yaml_file.name}: YAML did not parse to dict"
                )
            except yaml.YAMLError as exc:
                pytest.fail(f"{yaml_file.name}: YAML parse error: {exc}")

    def test_cron_has_three_config_files(self):
        """Should have heartbeat, morning-briefing, and standing-orders configs."""
        yaml_files = {f.stem for f in CRON_DIR.glob("*.yaml")}
        expected = {"heartbeat", "morning-briefing", "standing-orders"}
        missing = expected - yaml_files
        assert not missing, f"Missing cron config files: {missing}"
