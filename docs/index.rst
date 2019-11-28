Documentation for ibp webapp
============================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

SQLAlchemy Models
`````````````````
.. automodule:: ibp.models

Model Types
-----------
.. autoclass:: ibp.models.Inmate
    :members:
    :exclude-members: query_class

Column Types
------------
.. autodata:: ibp.models.Jurisdiction
.. autoclass:: ibp.models.ReleaseDate

Utility Types
-------------
.. autoclass:: ibp.models.InmateQuery
    :members:

.. autoclass:: ibp.models.HasInmateIndexKey
