import re
import json
from xml.etree.cElementTree import fromstring
from functools import partial
from collections import namedtuple
from contextlib import contextmanager
import threading
import time
from wsgiref.simple_server import make_server, WSGIRequestHandler
import logging
from tempfile import mkdtemp
from shutil import rmtree

import pytest
from mock import Mock
from webtest import TestApp
from webob.request import environ_add_POST
from sqlalchemy import create_engine
from pyramid.paster import bootstrap
import html5lib
from selenium import webdriver
from selenium.webdriver.support.ui import Select

from six import text_type


def pytest_addoption(parser):
    # The app ini file to be used for testing should be specified:
    parser.addoption("--appini", default='development.ini', help="app conf")


@pytest.fixture
def dbschema():
    from clld.db.meta import Base

    engine = create_engine('sqlite://')
    result = []

    def dump(sql):
        result.append(sql.compile(dialect=engine.dialect).string)

    mock_engine = create_engine(engine.url, strategy='mock', executor=dump)
    Base.metadata.create_all(mock_engine, checkfirst=False)
    return ''.join(result)


@pytest.fixture
def db():
    from clld.db.meta import Base, DBSession, VersionedDBSession

    engine = create_engine('sqlite://')
    Base.metadata.create_all(bind=engine)
    DBSession.configure(bind=engine)
    VersionedDBSession.configure(bind=engine)
    yield engine
    DBSession.close()
    VersionedDBSession.close()


@pytest.fixture
def data(db):
    yield db


@pytest.fixture
def env(data, pytestconfig):
    _env = bootstrap(pytestconfig.getoption('appini'))
    _env['request'].translate = lambda s, **kw: s
    return _env


def _add_header(headers, name, value):
    """Add (name, value) to headers.

    >>> headers = []
    >>> assert _add_header(headers, 'n', 'v') == [('n', 'v')]
    >>> headers = {}
    >>> assert _add_header(headers, 'n', 'v') == {'n': 'v'}
    """
    if isinstance(headers, dict):
        headers[name] = str(value)
    else:  # pragma: no cover
        headers.append((name, str(value)))


class ExtendedTestApp(TestApp):

    """WebTest TestApp with extended support for evaluation of responses."""

    parsed_body = None

    def get(self, *args, **kw):
        kw.setdefault('headers', {})
        if kw.pop('xhr', False):
            _add_header(kw['headers'], 'x-requested-with', 'XMLHttpRequest')
        accept = kw.pop('accept', False)
        if accept:
            _add_header(kw['headers'], 'accept', accept)
        kw.setdefault('status', 200)
        body_parser = kw.pop('_parse_body', None)
        res = super(ExtendedTestApp, self).get(*args, **kw)
        if body_parser and res.status_int < 300:
            self.parsed_body = body_parser(res.body)
        return res

    def get_html(self, *args, **kw):
        docroot = kw.pop('docroot', None)
        res = self.get(*args, _parse_body=html5lib.parse, **kw)
        child_nodes = list(self.parsed_body.getchildren())
        assert child_nodes
        if docroot:
            assert list(child_nodes[1].getchildren())[0].tag.endswith(docroot)
        return res

    def get_json(self, *args, **kw):
        _loads = lambda s: json.loads(text_type(s, encoding='utf8'))
        return self.get(*args, _parse_body=_loads, **kw)

    def get_xml(self, *args, **kw):
        return self.get(*args, _parse_body=fromstring, **kw)

    def get_dt(self, _path, *args, **kw):
        if 'sEcho=' not in _path:
            sep = '&' if '?' in _path else '?'
            _path = _path + sep + 'sEcho=1'
        kw.setdefault('xhr', True)
        return self.get_json(_path, *args, **kw)


class Route(Mock):
    """Mock a pyramid Route object."""
    def __init__(self, name='home'):
        super(Mock, self).__init__()
        self.name = name


def _set_request_property(req, k, v):
    if k == 'is_xhr':
        req.environ['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest' if v else ''
    elif k == 'params':
        environ_add_POST(req.environ, v)
    elif k == 'matched_route':
        setattr(req, k, Route(v))
    else:  # pragma: no cover
        setattr(req, k, v)


@contextmanager
def _request(env, **props):
    _cache = {}
    for k, v in props.items():
        _cache[k] = getattr(env['request'], k, None)
        _set_request_property(env['request'], k, v)

    yield env['request']

    for k, v in _cache.items():
        _set_request_property(env['request'], k, v)
    env['request'].environ.pop('HTTP_X_REQUESTED_WITH', None)
    environ_add_POST(env['request'].environ, {})


@pytest.fixture
def request_factory(env):
    return partial(_request, env)


@contextmanager
def _utility(env, utility, interface):
    env['registry'].registerUtility(utility, interface)
    yield
    env['registry'].unregisterUtility(utility, interface)


@pytest.fixture
def utility_factory(env):
    return partial(_utility, env)


@pytest.fixture
def app(env):
    return ExtendedTestApp(env['app'])



class Handler(WSGIRequestHandler):

    """Logging HTTP request handler."""

    def log_message(self, *args, **kw):
        return


class ServerThread(threading.Thread):

    """Run WSGI server on a background thread.

    Pass in WSGI app object and serve pages from it for Selenium browser.
    """

    def __init__(self, app, host='127.0.0.1:8880'):
        threading.Thread.__init__(self)
        self.app = app
        self.host, self.port = host.split(':')
        self.srv = None

    def run(self):
        """Open WSGI server to listen to HOST_BASE address."""
        self.srv = make_server(self.host, int(self.port), self.app, handler_class=Handler)
        try:
            self.srv.serve_forever()
        except:
            import traceback
            traceback.print_exc()
            # Failed to start
            self.srv = None

    def quit(self):
        if self.srv:
            self.srv.shutdown()


class PageObject(object):  # pragma: no cover

    """Virtual base class for objects we wish to interact with in selenium tests."""

    def __init__(self, browser, eid, url=None):
        """Initialize.

        :param browser: The selenium webdriver instance.
        :param eid: Element id of a dom object.
        :param url: If specified, we first navigate to this url.
        """
        self.browser = browser
        if url:
            self.browser.get(url)
        self.eid = eid

    @property
    def e(self):
        try:
            return self.browser.find_element_by_id(self.eid)
        except:
            return self.browser.find_element_by_class_name(self.eid)


class Map(PageObject):  # pragma: no cover

    """PageObject to interact with maps."""

    def __init__(self, browser, eid=None, url=None, sleep=2):
        super(Map, self).__init__(browser, eid or 'map-container', url=url)
        time.sleep(sleep)

    def test_show_marker(self, index=0):
        time.sleep(0.5)
        assert not self.e.find_elements_by_class_name('leaflet-popup-content')
        marker = self.e.find_elements_by_class_name('leaflet-marker-icon')
        marker[0].click()
        time.sleep(0.9)
        assert self.e.find_elements_by_class_name('leaflet-popup-content')

    def test_show_legend(self, name='iconsize'):
        e = self.e.find_element_by_id('legend-%s-container' % name)
        assert not e.is_displayed()
        opener = self.e.find_element_by_id('legend-%s-opener' % name)
        opener.click()
        time.sleep(0.3)
        assert e.is_displayed()
        opener.click()  # TODO: better test would be to click somewhere else!
        time.sleep(0.3)
        assert not e.is_displayed()


class DataTable(PageObject):  # pragma: no cover

    """PageObject to interact with DataTables."""

    info_pattern = re.compile('\s+'.join([
        'Showing', '(?P<offset>[0-9,]+)',
        'to', '(?P<limit>[0-9,]+)',
        'of', '(?P<filtered>[0-9,]+)',
        'entries(\s*\(filtered from (?P<total>[0-9,]+) total entries\))?',
    ]))

    def __init__(self, browser, eid=None, url=None):
        time.sleep(0.5)
        super(DataTable, self).__init__(browser, eid or 'dataTables_wrapper', url=url)

    def get_info(self):
        """Parse the DataTables result info."""
        fieldnames = 'offset limit filtered total'
        res = []
        info = self.e.find_element_by_class_name('dataTables_info')
        m = self.info_pattern.search(info.text.strip())
        for n in fieldnames.split():
            n = m.group(n)
            if n:
                n = int(n.replace(',', ''))
            res.append(n)
        return namedtuple('Info', fieldnames)(*res)

    def get_first_row(self):
        """Return a list with text-values of the cells of the first table row."""
        table = None
        for t in self.e.find_elements_by_tag_name('table'):
            if 'dataTable' in t.get_attribute('class'):
                table = t
                break
        assert table
        tr = table.find_element_by_tag_name('tbody').find_element_by_tag_name('tr')
        res = [td.text.strip() for td in tr.find_elements_by_tag_name('td')]
        return res

    def filter(self, name, value):
        """filter the table by using value for the column specified by name.

        Note that this abstracts the different ways filter controls can be implemented.
        """
        filter_ = self.e.find_element_by_id('dt-filter-%s' % name)
        if filter_.find_elements_by_tag_name('option'):
            filter_ = Select(filter_)
            filter_.select_by_visible_text(value)
        else:
            filter_.send_keys(value)
        time.sleep(2.5)

    def sort(self, label, sleep=2.5):
        """Trigger a table sort by clicking on the th Element specified by label."""
        sort = None
        for e in self.e.find_elements_by_xpath("//th"):
            if 'sorting' in e.get_attribute('class') and e.text.strip().startswith(label):
                sort = e
        assert sort
        sort.click()
        time.sleep(sleep)

    def download(self, fmt):
        opener = self.e.find_element_by_id('dt-dl-opener')
        link = self.e.find_element_by_id('dt-dl-%s' % fmt)
        assert not link.is_displayed()
        opener.click()
        assert link.is_displayed()
        link.click()
    

class Selenium(object):
    def __init__(self, app, host, downloads):
        self.host = host
        self.downloads = downloads
        profile = webdriver.firefox.firefox_profile.FirefoxProfile()
        profile.set_preference("browser.download.folderList", 2)
        profile.set_preference("browser.download.manager.showWhenStarting", False)
        profile.set_preference("browser.download.dir", downloads)
        profile.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/x-bibtex")
        self.browser = webdriver.Firefox(firefox_profile=profile)
        self.server = ServerThread(app, host)

    def url(self, path):
        return 'http://%s%s' % (self.host, path)

    def get_map(self, path, eid=None, sleep=2):
        return Map(self.browser, eid=eid, url=self.url(path), sleep=sleep)

    def get_datatable(self, path, eid=None):
        return DataTable(self.browser, eid=eid, url=self.url(path))


@pytest.fixture(scope='module')
def selenium(pytestconfig):
    selenium_logger = logging.getLogger('selenium.webdriver.remote.remote_connection')
    selenium_logger.setLevel(logging.WARNING)

    res = Selenium(
        bootstrap(pytestconfig.getoption('appini'))['app'], '127.0.0.1:8880', mkdtemp())
    res.server.start()
    time.sleep(0.3)
    assert res.server.srv
    yield res
    res.browser.quit()
    res.server.quit()
    rmtree(res.downloads)
