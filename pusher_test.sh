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

# Unit tests for pusher.par

# Trick to chase the symlink before the docker build.
cp pusher.par pusher2.par

# Generate a fresh random image to avoid completely
# incremental pushes.
function generate_image() {
  local target=$1

  cat > Dockerfile <<EOF
FROM alpine
RUN head -c100 /dev/urandom > /tmp/random.txt
EOF
  docker build -t random .
  docker save -o "${target}" random
  docker rmi -f random
}


# Sanity test that credentials are properly configured.
function test_sanity() {
  local image=$1
  local random_image="direct.$RANDOM.tar"
  generate_image "${random_image}"

  docker load -i "${random_image}"
  docker tag random "${image}"
  docker push "${image}"
  docker rmi -f random "${image}"
}

# Test pushing an image by just invoking the pusher
function test_pusher() {
  local image=$1
  local random_image="direct.$RANDOM.tar"
  generate_image "${random_image}"

  # Test it in our current environment.
  pusher.par --name="${image}" --tarball="${random_image}"
}

# Test pushing an image from inside a docker container with a
# certain base / entrypoint
function test_base() {
  local image=$1
  local entrypoint=$2
  local base_image=$3
  local random_image="in-image.$RANDOM.tar"
  generate_image "${random_image}"

  echo Testing pusher env: ${base_image} entrypoint: ${entrypoint}
  # TODO(user): use a temp dir
  cat > Dockerfile <<EOF
FROM ${base_image}
ADD pusher2.par /pusher.par
EOF

  docker build -t pusher_test .
  docker run -i --rm --entrypoint="${entrypoint}" \
    -v "${HOME}/.docker/:/root/.docker/" \
    -v "${random_image}:/${random_image}" pusher_test \
    /pusher.par --name="${image}" --tarball="/${random_image}"
  docker rmi pusher_test
}

function test_image() {
  local image=$1

  echo "TESTING: ${image}"

  test_sanity "${image}"

  test_pusher "${image}"

  # TODO(user): Test inside of docker images.
  # test_base "${image}" python2.7 python:2.7
  # test_base "${image}" python2.7 gcr.io/cloud-builders/bazel
}

# Test pushing a trivial image.
# The registered credential only has access to this repository,
# which is only used for testing.
test_image gcr.io/containerregistry-releases/pusher-testing:latest

# Test pushing to DockerHub
test_image index.docker.io/googlecontainerregistrytesting/pusher-testing:latest

# Test pushing to Bintray.io
test_image googlecontainerregistrytesting-docker-test-repo.bintray.io/testing/pusher-testing:latest

# TODO(user): Enable once Quay supports v2.2
# # Test pushing to Quay.io
# test_image quay.io/googlecontainerregistrytesting/pusher-testing:latest

# TODO(user): Enable once SNI issues are resolved.
# # Test pushing to Gitlab
# test_image registry.gitlab.com/googlecontainerregistrytesting/pusher-testing/image:latest
