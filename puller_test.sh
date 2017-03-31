#!/bin/bash -e

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

# Unit tests for puller.par

# Test it in our current environment.
puller.par --name=gcr.io/google-containers/pause:2.0 --tarball=/tmp/foo.tar

# Trick to chase the symlink before the docker build.
cp puller.par puller2.par

function test_base() {
  local entrypoint=$1
  local base_image=$2

  echo Testing puller env: ${base_image} entrypoint: ${entrypoint}
  # TODO(user): use a temp dir
  cat > Dockerfile <<EOF
FROM ${base_image}
ADD puller2.par /puller.par
EOF

  docker build -t puller_test .

  docker run -i --rm --entrypoint="${entrypoint}" puller_test \
    /puller.par --name=gcr.io/google-containers/pause:2.0 --tarball=/tmp/foo.tar

  docker rmi puller_test
}

test_base python2.7 python:2.7
test_base python2.7 gcr.io/cloud-builders/bazel
