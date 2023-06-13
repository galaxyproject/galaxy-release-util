
.. image:: https://badge.fury.io/py/galaxy-release-utils.svg
   :target: https://pypi.org/project/galaxy-release-utils/



Overview
--------

Scripts to create new Galaxy_ releases.

* Code: https://github.com/galaxyproject/galaxy-release-util

.. _Galaxy: http://galaxyproject.org/

Development
-----------

Tests can be executed with `tox`.

Release Checklist
-----------------

* Update HISTORY.rst
* Update version number in setup.cfg
* Run `make dist`
* Tag a new version and create a release from the GitHub interface
