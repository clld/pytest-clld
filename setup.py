from setuptools import setup

setup(
    name="pytest-clld",
    packages = ['pytest_clld'],
    install_requires=['pytest>=3.1'],
    entry_points = {
        'pytest11': [
            'clld = pytest_clld.plugin',
        ]
    },
    classifiers=[
        "Framework :: Pytest",
    ],
)
