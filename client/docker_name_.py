# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This package defines Tag a way of representing an image uri."""



import os
import sys



class BadNameException(Exception):
  """Exceptions when a bad docker name is supplied."""


_REPOSITORY_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789_-./'
_TAG_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789_-.ABCDEFGHIJKLMNOPQRSTUVWXYZ'
# These have the form: sha256:<hex string>
_DIGEST_CHARS = 'sh:0123456789abcdef'

# TODO(user): Add a flag to allow specifying custom app name to be appended to
# useragent.
_APP = os.path.basename(sys.argv[0]) if sys.argv[0] else 'console'
USER_AGENT = '//containerregistry/client:%s' % _APP


def _check_element(
    name,
    element,
    characters,
    min_len,
    max_len
):
  """Checks a given named element matches character and length restrictions.

  Args:
    name: the name of the element being validated
    element: the actual element being checked
    characters: acceptable characters for this element, or None
    min_len: minimum element length, or None
    max_len: maximum element length, or None

  Raises:
    BadNameException: one of the restrictions was not met.
  """
  length = len(element)
  if min_len and length < min_len:
    raise BadNameException('Invalid %s: %s, must be at least %s characters'
                           % (name, element, min_len))

  if max_len and length > max_len:
    raise BadNameException('Invalid %s: %s, must be at most %s characters'
                           % (name, element, max_len))

  if element.strip(characters):
    raise BadNameException('Invalid %s: %s, acceptable characters include: %s'
                           % (name, element, characters))


def _check_repository(repository):
  _check_element('repository', repository, _REPOSITORY_CHARS, 4, 255)


def _check_tag(tag):
  _check_element('tag', tag, _TAG_CHARS, 1, 127)


def _check_digest(digest):
  _check_element('digest', digest, _DIGEST_CHARS, 7 + 64, 7 + 64)


class Registry(object):
  """Stores a docker registry name in a structured form."""

  def __init__(self, name):
    if not name:
      raise BadNameException('A Docker registry name must be specified')

    self._registry = name

  @property
  def registry(self):
    return self._registry

  def __str__(self):
    return self.registry

  def scope(self, unused_action):
    # The only resource under 'registry' is 'catalog'. http://goo.gl/N9cN9Z
    return 'registry:catalog:*'


class Repository(Registry):
  """Stores a docker repository name in a structured form."""

  def __init__(self, name):
    if not name:
      raise BadNameException('A Docker image name must be specified')

    parts = name.split('/', 1)
    if len(parts) != 2:
      raise self._validation_exception(name)
    super(Repository, self).__init__(parts[0])

    self._repository = parts[1]
    _check_repository(self._repository)

  def _validation_exception(self, name):
    return BadNameException('Docker image name must have the form: '
                            'registry/repository, saw: %s' % name)

  @property
  def repository(self):
    return self._repository

  def __str__(self):
    return '{registry}/{repository}'.format(
        registry=self.registry, repository=self.repository)

  def scope(self, action):
    return 'repository:{resource}:{action}'.format(
        resource=self._repository,
        action=action)


class Tag(Repository):
  """Stores a docker repository tag in a structured form."""

  def __init__(self, name):
    parts = name.rsplit(':', 1)
    if len(parts) != 2:
      raise self._validation_exception(name)

    self._tag = parts[1]
    _check_tag(self._tag)
    super(Tag, self).__init__(parts[0])

  def _validation_exception(self, name):
    return BadNameException('Docker image name must be fully qualified (e.g.'
                            'registry/repository:tag) saw: %s' % name)

  @property
  def tag(self):
    return self._tag

  def __str__(self):
    return '{base}:{tag}'.format(base=super(Tag, self).__str__(), tag=self.tag)

  def __eq__(self, other):
    return (bool(other) and self.repository == other.repository and
            self.tag == other.tag)

  def __ne__(self, other):
    return not self.__eq__(other)

  def __hash__(self):
    return hash((self.repository, self.tag))


class Digest(Repository):
  """Stores a docker repository digest in a structured form."""

  def __init__(self, name):
    parts = name.split('@')
    if len(parts) != 2:
      raise self._validation_exception(name)

    self._digest = parts[1]
    _check_digest(self._digest)
    super(Digest, self).__init__(parts[0])

  def _validation_exception(self, name):
    return BadNameException('Docker image name must be fully qualified (e.g.'
                            'registry/repository@digest) saw: %s' % name)

  @property
  def digest(self):
    return self._digest

  def __str__(self):
    return '{base}@{digest}'.format(base=super(Digest, self).__str__(),
                                    digest=self.digest)

  def __eq__(self, other):
    return (bool(other) and self._repository == other.repository and
            self.digest == other.digest)

  def __ne__(self, other):
    return not self.__eq__(other)

  def __hash__(self):
    return hash((self.repository, self.digest))
