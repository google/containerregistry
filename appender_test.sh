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

# Trick to chase the symlink before the docker build.
cp appender.par appender2.par

# Test appending to an image.
function test_appender() {
  local src=$1
  local dst=$2
  tmp=$(mktemp -d)
  appdir="$tmp/app"
  mkdir -p "$appdir"
  head -c100 /dev/urandom > $appdir/random.txt
  tar -czf layer.tar.gz -C $tmp app/
  # Test it in our current environment.
  appender.par --src-image="${src}" --dst-image="${dst}" --tarball=layer.tar.gz
  docker pull "${dst}"
  docker run -v "${appdir}":/original "${dst}" \
    cmp /original/random.txt /app/random.txt
}


test_appender gcr.io/google-appengine/nodejs:latest \
  gcr.io/containerregistry-releases/appender-testing:latest

