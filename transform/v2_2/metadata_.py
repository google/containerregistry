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
"""This package manipulates v2.2 image configuration metadata."""



from collections import namedtuple
import copy
import os


_OverridesT = namedtuple('OverridesT', [
    'layers', 'entrypoint', 'cmd', 'env', 'labels', 'ports',
    'volumes', 'workdir', 'user', 'author', 'created_by'
])


class Overrides(_OverridesT):
  """Docker image configuration options."""

  def __new__(
      cls,
      layers=None,
      entrypoint=None,
      cmd=None,
      user=None,
      labels=None,
      env=None,
      ports=None,
      volumes=None,
      workdir=None,
      author=None,
      created_by=None):
    """Constructor."""
    return super(Overrides, cls).__new__(
        cls, layers=layers, entrypoint=entrypoint, cmd=cmd, user=user,
        labels=labels, env=env, ports=ports, volumes=volumes, workdir=workdir,
        author=author, created_by=created_by)


# NOT THREADSAFE
def _Resolve(
    value,
    environment
):
  """Resolves environment variables embedded in the given value."""
  outer_env = os.environ
  try:
    os.environ = environment
    return os.path.expandvars(value)
  finally:
    os.environ = outer_env


# TODO(user): Use a typing.Generic?
def _DeepCopySkipNull(
    data
):
  """Do a deep copy, skipping null entry."""
  if isinstance(data, dict):
    return dict((_DeepCopySkipNull(k), _DeepCopySkipNull(v))
                for k, v in data.iteritems() if v is not None)
  return copy.deepcopy(data)


def _KeyValueToDict(
    pair
):
  """Converts an iterable object of key=value pairs to dictionary."""
  d = dict()
  for kv in pair:
    (k, v) = kv.split('=', 1)
    d[k] = v
  return d


def _DictToKeyValue(
    d
):
  return ['%s=%s' % (k, d[k]) for k in sorted(d.keys())]


def Override(
    data,
    options,
    architecture='amd64',
    operating_system='linux'
):
  """Create an image config possibly based on an existing one.

  Args:
    data: A dict of Docker image config to base on top of.
    options: Options specific to this image which will be merged with any
             existing data
    architecture: The architecture to write in the metadata (default: amd64)
    operating_system: The os to write in the metadata (default: linux)

  Returns:
    Image config for the new image
  """
  defaults = _DeepCopySkipNull(data)

  # dont propagate non-spec keys
  output = dict()
  output['created'] = '0001-01-01T00:00:00Z'
  output['author'] = options.author or 'Unknown'
  output['architecture'] = architecture
  output['os'] = operating_system

  output['config'] = defaults.get('config', {})

  if options.entrypoint:
    output['config']['Entrypoint'] = options.entrypoint
  if options.cmd:
    output['config']['Cmd'] = options.cmd
  if options.user:
    output['config']['User'] = options.user

  if options.env:
    # Build a dictionary of existing environment variables (used by _Resolve).
    environ_dict = _KeyValueToDict(output['config'].get('Env', []))
    # Merge in new environment variables, resolving references.
    for k, v in options.env.iteritems():
      # Resolve handles scenarios like "PATH=$PATH:...".
      environ_dict[k] = _Resolve(v, environ_dict)
    output['config']['Env'] = _DictToKeyValue(environ_dict)

  # TODO(user) Label is currently docker specific
  if options.labels:
    label_dict = _KeyValueToDict(output['config'].get('Label', []))
    for k, v in options.labels.iteritems():
      label_dict[k] = v
    output['config']['Label'] = _DictToKeyValue(label_dict)

  if options.ports:
    if 'ExposedPorts' not in output['config']:
      output['config']['ExposedPorts'] = {}
    for p in options.ports:
      if '/' in p:
        # The port spec has the form 80/tcp, 1234/udp
        # so we simply use it as the key.
        output['config']['ExposedPorts'][p] = {}
      else:
        # Assume tcp
        output['config']['ExposedPorts'][p + '/tcp'] = {}

  if options.volumes:
    if 'Volumes' not in output['config']:
      output['config']['Volumes'] = {}
    for p in options.volumes:
      output['config']['Volumes'][p] = {}

  if options.workdir:
    output['config']['WorkingDir'] = options.workdir

  # diff_ids are ordered from bottom-most to top-most
  diff_ids = defaults.get('rootfs', {}).get('diff_ids', [])
  layers = options.layers if options.layers else []
  diff_ids += ['sha256:%s' % l for l in layers]
  output['rootfs'] = {
      'type': 'layers',
      'diff_ids': diff_ids,
  }

  # history is ordered from bottom-most layer to top-most layer
  history = defaults.get('history', [])
  # docker only allows the child to have one more history entry than the parent
  history += [{
      'created': '0001-01-01T00:00:00Z',
      'created_by': options.created_by or 'Unknown',
      'author': options.author or 'Unknown'}]
  output['history'] = history

  return output
