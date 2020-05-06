from setuptools import setup


setup(
    name='pytest-clld',
    version='1.0.1',
    packages=['pytest_clld'],
    install_requires=[
        'pytest>=3.6', 
        'clld',
        'sqlalchemy>=1.0',
        'WebTest>=1.3.1',
        'pyramid>=1.6',
        'mock',
        'html5lib',
        'webob',
        'selenium>=3.8.1',
    ],
    entry_points={
        'pytest11': [
            'pytest_clld = pytest_clld.plugin',
        ]
    },
    classifiers=[
        'Framework :: Pytest',
    ],
)
