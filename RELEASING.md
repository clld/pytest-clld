
Releasing pytest-clld
=====================

- Change version to the new version number in `setup.py`.

- Bump version number:
```
git commit -a -m"bumped version number"
```

- Create a release tag:
```
git tag -a v<version> -m"first version to be released on pypi"
```

- Release to PyPI:
```
git checkout tags/v$1
rm dist/*
python -m build -n
twine upload dist/*
```

- Push to github:
```
git push origin
git push --tags
```
