"""Tests for the buyer module (unit tests — no browser)."""

from unittest.mock import patch

from resell_bot.core.buyer import BuyJob, BuyStep, STEP_LABELS, get_job, start_buy, _active_jobs


class TestBuyJob:
    def test_to_dict_momox(self):
        job = BuyJob(
            alert_id=1,
            product_url="https://momox-shop.fr/M01234.html",
            title="Fondation",
            price=5.0,
            platform="momox_shop",
        )
        d = job.to_dict()
        assert d["platform"] == "momox_shop"
        assert d["platform_label"] == "Momox"
        assert d["step"] == "pending"
        assert d["step_label"] == STEP_LABELS[BuyStep.PENDING]

    def test_to_dict_recyclivre(self):
        job = BuyJob(
            alert_id=2,
            product_url="https://recyclivre.com/products/12345",
            title="Dune",
            price=3.5,
            platform="recyclivre",
        )
        d = job.to_dict()
        assert d["platform"] == "recyclivre"
        assert d["platform_label"] == "RecycLivre"

    def test_platform_label_unknown(self):
        job = BuyJob(
            alert_id=3,
            product_url="https://example.com",
            title="Test",
            price=1.0,
            platform="ebay",
        )
        assert job.platform_label == "ebay"

    def test_steps_tracking(self):
        job = BuyJob(
            alert_id=4,
            product_url="https://example.com",
            title="Test",
            price=1.0,
        )
        job.step = BuyStep.COMPLETED
        job.steps_done.append("Opened page")
        d = job.to_dict()
        assert len(d["steps_done"]) == 1
        assert d["step"] == "completed"

    def test_get_job_returns_none(self):
        assert get_job(99999) is None

    def test_job_tracker(self):
        job = BuyJob(
            alert_id=100,
            product_url="https://example.com",
            title="Test",
            price=1.0,
        )
        _active_jobs[100] = job
        assert get_job(100) is job
        del _active_jobs[100]

    def test_all_steps_have_labels(self):
        for step in BuyStep:
            assert step in STEP_LABELS

    def test_job_lifecycle(self):
        _active_jobs.clear()

        job = BuyJob(alert_id=10, product_url="x", title="T", price=1.0)
        assert job.step == BuyStep.PENDING
        _active_jobs[10] = job

        job.step = BuyStep.COMPLETED
        assert get_job(10).step == BuyStep.COMPLETED
        _active_jobs.clear()
