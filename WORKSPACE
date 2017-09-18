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
workspace(name = "containerregistry")

git_repository(
    name = "io_bazel_rules_python",
    commit = "7f4cc9244dac7637d514e4f86364507681dda37e",
    remote = "https://github.com/bazelbuild/rules_python.git",
)

load(
    "@io_bazel_rules_python//python:pip.bzl",
    "pip_import",
    "pip_repositories",
)

pip_repositories()

pip_import(
    name = "pip_containerregistry",
    requirements = "//:requirements.txt",
)

load("@pip_containerregistry//:requirements.bzl", "pip_install")

pip_install()

# For packaging python tools.
git_repository(
    name = "subpar",
    remote = "https://github.com/google/subpar",
    commit = "7e12cc130eb8f09c8cb02c3585a91a4043753c56",
)
