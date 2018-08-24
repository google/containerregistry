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

# Unit tests for digester.par

# Trick to chase the symlink before the docker build.
cp digester.par digester2.par
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

# Test pushing an image by just invoking the digester
function test_digester() {
  local image=$1
  local random_image="direct.$RANDOM.tar"
  local output_file="digest.txt"
  generate_image "${random_image}"

  # Test it in our current environment.
  # Output has following format: {image} was published with digest: sha256:...
  output="$(pusher.par --name="${image}" --tarball="${random_image}")"
  push_digest="$(echo "${output##* }")"

  digester.par --tarball="${random_image}" --output-digest="${output_file}"
  digest="$(cat ${output_file})"
  if [ "${push_digest}" != "${digest}" ]; then
    echo "Digests don't match."
    exit 1
  fi
}

function test_image() {
  local image=$1

  echo "TESTING: ${image}"

  test_digester "${image}"
}


# Test pushing a trivial image.
# The registered credential only has access to this repository, which is only used for testing.
test_image gcr.io/containerregistry-releases/digest-testing:latest
