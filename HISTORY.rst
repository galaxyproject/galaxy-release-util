History
-------

.. to_doc


------------------
0.3.2 (20-01-2026)
------------------
* Don't add ``requirements.txt`` to ``meta_package.modified_paths`` by @nsoranzo in https://github.com/galaxyproject/galaxy-release-util/pull/39
* Changes to Release Issue Template by @ahmedhamidawan in https://github.com/galaxyproject/galaxy-release-util/pull/33
* Restructure release notes to account for GitHub notes by @ahmedhamidawan in https://github.com/galaxyproject/galaxy-release-util/pull/40
* Remove the "plus one week" timeframe separation between freezing and branching by @ahmedhamidawan in https://github.com/galaxyproject/galaxy-release-util/pull/41
* Add Release Manager Task Instructions by @guerler in https://github.com/galaxyproject/galaxy-release-util/pull/42
* Update galaxy-client dependency version during point releases by @dannon in https://github.com/galaxyproject/galaxy-release-util/pull/43

------------------
0.3.1 (01-08-2025)
------------------
* Rebuild meta dependencies by @mvdbeek in https://github.com/galaxyproject/galaxy-release-util/pull/38

------------------
0.3.0 (20-06-2025)
------------------
* Fix link to release docs by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/21
* Remove outdated step from release issue template by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/22
* Add tool+wf tests step to issue template, swap release notes step w/deployment on main by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/24
* Misc. refactoring and enhancements to create_point_release by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/25
* Update release notes templates by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/26
* Mics fixes by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/27
* Remove create-release step from issue template by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/28
* Don't remove newline at the end of ``setup.cfg`` files by @nsoranzo in https://github.com/galaxyproject/galaxy-release-util/pull/29
* Remove TS items from release publication issue template by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/30
* Build and upload meta package, merge dependencies into requirements.txt by @mvdbeek in https://github.com/galaxyproject/galaxy-release-util/pull/31
* Bump and build client version by @mvdbeek in https://github.com/galaxyproject/galaxy-release-util/pull/32
* Commit metapackage requirements.txt by @natefoo in https://github.com/galaxyproject/galaxy-release-util/pull/34
* Add web_client to packages to build by @natefoo in https://github.com/galaxyproject/galaxy-release-util/pull/35
* Remove web_client and meta from package list since they were added to the package dag file by @natefoo in https://github.com/galaxyproject/galaxy-release-util/pull/36

------------------
0.2.0 (02-12-2024)
------------------
* Misc. refactoring and enhancements to bootstrap_history by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/19
* Fix strip_release bug by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/20

-------------------
0.1.11 (20-05-2024)
-------------------
* Update release issue template by @jdavcs in  https://github.com/galaxyproject/galaxy-release-util/pull/16
* Fix typos in release issue template by @jdavcs in  https://github.com/galaxyproject/galaxy-release-util/pull/18

------------------
0.1.9 (02-05-2024)
------------------
* Fix release script if multiple bug fixes subheadings in changelog by @mvdbeek in https://github.com/galaxyproject/galaxy-release-util/pull/15

------------------
0.1.8 (02-05-2024)
------------------
* Add mypy to CI under python 3.8 by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/11
* Misc. updates  by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/12
* Misc. updates to script generating the release publication issue by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/13
* Fix link to docs on point releases by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/14

------------------
0.1.7 (21-02-2024)
------------------
* Misc. updates to script by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/9

------------------
0.1.6 (14-02-2024)
------------------
* Ignore commit without PR by @mvdbeek in https://github.com/galaxyproject/galaxy-release-util/pull/4
* Rename sections: "new things" > "things" by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/6
* Use semantic headings by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/5
* Ignore empty lines, comments when reading in packages_by_dep_dag.txt file by @jdavcs in https://github.com/galaxyproject/galaxy-release-util/pull/7
* Update release process template to current process by @mvdbeek in https://github.com/galaxyproject/galaxy-release-util/pull/8

------------------
0.1.5 (14-09-2023)
------------------
* Bootstrap history fixes for regenerating existing docs

------------------
0.1.4 (30-06-2023)
------------------
* Skip empty prerelease changelog when parsing changelog

------------------
0.1.3 (28-06-2023)
------------------
* Add step/checkbox on updating db revision identifier
* Bootstrap history fixes

------------------
0.1.2 (12-06-2023)
------------------
* Fix isinstance assertion

------------------
0.1.1 (12-06-2023)
------------------
* Add simplified makefile, development instruction
* Fix project description

------------------
0.1.0 (12-06-2023)
------------------

* Initial import from the Galaxy codebase
