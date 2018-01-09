from setuptools import setup

setup(
    name="pytest-clld",
    packages = ['pytest_clld'],
    entry_points = {
        'pytest11': [
            'clld = pytest_clld.plugin',
        ]
    },
    classifiers=[
        "Framework :: Pytest",
    ],
)
