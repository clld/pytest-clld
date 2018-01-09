import json
from xml.etree.cElementTree import fromstring
from functools import partial
from contextlib import contextmanager

import pytest
from mock import Mock
from webtest import TestApp
from webob.request import environ_add_POST
from sqlalchemy import create_engine
from pyramid.paster import bootstrap
import html5lib

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
    Base.metadata.bind = engine
    Base.metadata.create_all()
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
