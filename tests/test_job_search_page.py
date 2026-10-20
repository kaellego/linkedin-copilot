import unittest
import threading
from queue import Queue

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
    def test_wait_accepts_nested_title_label_on_details_panel(self):
        title = _Element("Analista de Suporte Técnico Pleno")

        class Job:
            def find_element(self, by, selector):
                return title

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
