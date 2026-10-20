import unittest
import threading
from queue import Queue
from unittest.mock import Mock
from selenium.common.exceptions import StaleElementReferenceException

from pages.job_search_page import JobSearchPage


class _Element:
    def __init__(self, label=None, displayed=True):
        self.label = label
        self.displayed = displayed

    def get_attribute(self, name):
        return self.label if name == "aria-label" else None

    def find_elements(self, by, selector):
        if selector == "[aria-label]" and self.label:
            return [self]
        if selector.startswith("button#jobs-apply-button-id"):
            return [_Element(displayed=True)]
        return []

    def is_displayed(self):
        return self.displayed


class ExternalJobDetailsTests(unittest.TestCase):
    def test_refreshes_job_card_by_stable_job_id(self):
        page = JobSearchPage.__new__(JobSearchPage)
        stale_card = Mock()
        stale_card.get_attribute.return_value = "old"
        current_card = Mock()
        current_card.get_attribute.return_value = "4477723228"
        page.driver = Mock()
        page.driver.find_elements.return_value = [stale_card, current_card]

        self.assertIs(page._refresh_job_card("4477723228", 0), current_card)

    def test_card_click_reacquires_after_stale_reference(self):
        page = JobSearchPage.__new__(JobSearchPage)
        old_card, current_card, clickable = Mock(), Mock(), Mock()
        old_card.get_attribute.side_effect = StaleElementReferenceException("redraw")
        current_card.get_attribute.return_value = "4477723228"
        current_card.find_element.return_value = clickable
        page.driver = Mock()
        page.driver.find_elements.return_value = [old_card, current_card]

        page._click_job_card("4477723228", 0)

        clickable.click.assert_called_once_with()

    def test_clicks_yes_when_offsite_confirmation_is_available(self):
        page = JobSearchPage.__new__(JobSearchPage)
        button = object()
        page.status_queue = Mock()
        page._find_clickable_element = Mock(return_value=button)
        page._click_external_apply_button = Mock()

        self.assertTrue(page._confirm_offsite_application())
        page._find_clickable_element.assert_called_once_with(page.OFFSITE_APPLY_CONFIRMATION_YES, 12)
        page._click_external_apply_button.assert_called_once_with(button)

    def test_reports_when_offsite_confirmation_does_not_appear(self):
        page = JobSearchPage.__new__(JobSearchPage)
        page.status_queue = Mock()
        page._find_clickable_element = Mock(return_value=None)
        page._click_external_apply_button = Mock()

        self.assertFalse(page._confirm_offsite_application())
        page._click_external_apply_button.assert_not_called()

    def test_wait_accepts_nested_title_label_on_details_panel(self):
        title = _Element("Candidatar-se à vaga de Assistente TI - Goiânia GO no site da empresa")

        class Job:
            def find_element(self, by, selector):
                return _Element("Assistente  TI - Goiânia GO with verification")

        panel = _Element()
        panel.find_elements = lambda by, selector: (
            [title] if selector == "[aria-label]" else [_Element()] if selector.startswith("button#jobs-apply-button-id") else []
        )

        class Driver:
            def find_elements(self, by, selector):
                return [panel] if selector == ".jobs-search__job-details--wrapper" else []

        page = JobSearchPage.__new__(JobSearchPage)
        page.driver = Driver()
        self.assertIs(page._wait_for_job_details(Job()), panel)

    def test_external_tab_monitor_does_not_switch_focus(self):
        class Driver:
            switch_to = None

            def __init__(self):
                self.reads = 0

            @property
            def window_handles(self):
                self.reads += 1
                return ["main", "apply"] if self.reads == 1 else ["main"]

        class FocusGuard:
            def window(self, handle):
                raise AssertionError("monitor must not change browser focus")

        page = JobSearchPage.__new__(JobSearchPage)
        page.driver = Driver()
        page.driver.switch_to = FocusGuard()
        page.stop_event = threading.Event()
        page.pause_event = threading.Event()
        page.status_queue = Queue()
        page._wait_for_external_tab_close("apply", "main")
        self.assertTrue(page.pause_event.is_set())

    def test_external_tab_discovery_does_not_switch_focus(self):
        class Driver:
            window_handles = ["main", "apply"]
            switch_to = None

        class FocusGuard:
            def window(self, handle):
                raise AssertionError("discovery must not change browser focus")

        page = JobSearchPage.__new__(JobSearchPage)
        page.driver = Driver()
        page.driver.switch_to = FocusGuard()
        self.assertEqual(page._find_external_destination("main", "main", timeout=0.1), "apply")


if __name__ == "__main__":
    unittest.main()
