import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "wake_streamlit.py"
SPEC = importlib.util.spec_from_file_location("wake_streamlit", SCRIPT_PATH)
wake_streamlit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(wake_streamlit)


class FakeLocator:
    def __init__(self, visible=False):
        self.visible = visible
        self.clicked = False

    @property
    def first(self):
        return self

    def is_visible(self):
        return self.visible

    def click(self):
        self.clicked = True


class FakeContext:
    def __init__(self, marker=False, wake_button=False):
        self.marker = FakeLocator(marker)
        self.wake_button = FakeLocator(wake_button)

    def get_by_text(self, _text, exact=False):
        return self.marker

    def get_by_role(self, _role, name=None):
        return self.wake_button


class FakePage(FakeContext):
    def __init__(self, marker=False, wake_button=False, frames=None):
        super().__init__(marker, wake_button)
        self.frames = frames or []


class WakeStreamlitTests(unittest.TestCase):
    def test_marker_can_be_found_inside_streamlit_iframe(self):
        page = FakePage(frames=[FakeContext(marker=True)])

        self.assertTrue(wake_streamlit.marker_is_visible(wake_streamlit.browser_contexts(page)))

    def test_wake_button_can_be_clicked_on_sleep_page(self):
        page = FakePage(wake_button=True)

        clicked = wake_streamlit.click_wake_button(wake_streamlit.browser_contexts(page))

        self.assertTrue(clicked)
        self.assertTrue(page.wake_button.clicked)

    def test_absent_marker_and_button_are_reported(self):
        page = FakePage(frames=[FakeContext()])

        self.assertFalse(wake_streamlit.marker_is_visible(wake_streamlit.browser_contexts(page)))
        self.assertFalse(wake_streamlit.click_wake_button(wake_streamlit.browser_contexts(page)))


if __name__ == "__main__":
    unittest.main()
