import re
import collections

from selenium.webdriver.support import ui
from selenium.webdriver.common.by import By

from . import _selenium_common


class Info(collections.namedtuple('Info', ['offset', 'limit', 'filtered', 'total'])):

    __slots__ = ()

    pattern = re.compile(r'\s+'.join([
        'Showing', '(?P<offset>[0-9,]+)',
        'to', '(?P<limit>[0-9,]+)',
        'of', '(?P<filtered>[0-9,]+)',
        r'entries(\s*\(filtered from (?P<total>[0-9,]+) total entries\))?',
    ]))

    @classmethod
    def fromtext(cls, text):
        ma = cls.pattern.search(text.strip())
        values = ma.group(*cls._fields)
        values = (int(v.replace(',', '')) if v else v for v in values)
        return cls._make(values)


class DataTable(_selenium_common.PageObject):  # pragma: no cover
    """PageObject to interact with DataTables."""

    def __init__(self, browser, eid=None, url=None):
        self.sleep(2)
        super(DataTable, self).__init__(browser, eid or 'dataTables_wrapper', url=url)

    def get_info(self):
        """Parse the DataTables result info."""
        info = self.e.find_element(By.CLASS_NAME, 'dataTables_info')
        return Info.fromtext(info.text)

    def get_first_row(self):
        """Return a list with text-values of the cells of the first table row."""
        table = None
        for t in self.e.find_elements(By.TAG_NAME, 'table'):
            if 'dataTable' in t.get_attribute('class'):
                table = t
                break
        assert table
        tr = table.find_element(By.TAG_NAME, 'tbody').find_element(By.TAG_NAME, 'tr')
        res = [td.text.strip() for td in tr.find_elements(By.TAG_NAME, 'td')]
        return res

    def filter(self, name, value, sleep_ticks=10):
        """filter the table by using value for the column specified by name.

        Note that this abstracts the different ways filter controls can be implemented.
        """
        filter_ = self.e.find_element(By.ID, 'dt-filter-%s' % name)
        if filter_.find_elements(By.TAG_NAME, 'option'):
            filter_ = ui.Select(filter_)
            filter_.select_by_visible_text(value)
        else:
            filter_.send_keys(value)
        self.sleep(sleep_ticks)

    def sort(self, label, sleep=2.5):
        """Trigger a table sort by clicking on the th Element specified by label."""
        sort = None
        for e in self.e.find_elements(By.XPATH, "//th"):
            if 'sorting' in e.get_attribute('class') and e.text.strip().startswith(label):
                sort = e
        assert sort
        sort.click()
        self.sleep(sleep, tick=1.0)

    def download(self, fmt):
        opener = self.e.find_element(By.ID, 'dt-dl-opener')
        link = self.e.find_element(By.ID, 'dt-dl-%s' % fmt)
        assert not link.is_displayed()
        opener.click()
        assert link.is_displayed()
        link.click()
