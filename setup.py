from setuptools import setup


setup(
    name="pytest-clld",
    version="0.1",
    packages=['pytest_clld'],
    install_requires=[
        'pytest>=3.1', 
        'clld',
        'sqlalchemy>=1.0',
        'WebTest>=1.3.1',
        'six',
        'pyramid>=1.6',
        'mock',
        'html5lib>=1.0.1',
        'webob',
    ],
    entry_points={
        'pytest11': [
            'clld = pytest_clld',
        ]
    },
    classifiers=[
        "Framework :: Pytest",
    ],
)
