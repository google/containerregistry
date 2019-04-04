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

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def repositories():
    """Load bazel dependencies."""

    http_archive(
        name = "httplib2",
        url = "https://codeload.github.com/httplib2/httplib2/tar.gz/v0.11.3",
        sha256 = "d9f568c183d1230f271e9c60bd99f3f2b67637c3478c9068fea29f7cca3d911f",
        strip_prefix = "httplib2-0.11.3/python2/httplib2/",
        type = "tar.gz",
        build_file_content = """
py_library(
   name = "httplib2",
   srcs = glob(["**/*.py"]),
   data = ["cacerts.txt"],
   visibility = ["//visibility:public"]
)""",
    )

    # Used by oauth2client
    http_archive(
        name = "six",
        url = "https://pypi.python.org/packages/source/s/six/six-1.9.0.tar.gz",
        sha256 = "e24052411fc4fbd1f672635537c3fc2330d9481b18c0317695b46259512c91d5",
        strip_prefix = "six-1.9.0/",
        type = "tar.gz",
        build_file_content = """
# Rename six.py to __init__.py
genrule(
    name = "rename",
    srcs = ["six.py"],
    outs = ["__init__.py"],
    cmd = "cat $< >$@",
)
py_library(
   name = "six",
   srcs = [":__init__.py"],
   visibility = ["//visibility:public"],
)""",
    )

    # Used for authentication in containerregistry
    http_archive(
        name = "oauth2client",
        url = "https://codeload.github.com/google/oauth2client/tar.gz/v4.0.0",
        sha256 = "7230f52f7f1d4566a3f9c3aeb5ffe2ed80302843ce5605853bee1f08098ede46",
        strip_prefix = "oauth2client-4.0.0/oauth2client/",
        type = "tar.gz",
        build_file_content = """
py_library(
   name = "oauth2client",
   srcs = glob(["**/*.py"]),
   visibility = ["//visibility:public"],
   deps = [
     "@httplib2//:httplib2",
     "@six//:six",
   ]
)""",
    )

    # Used for parallel execution in containerregistry
    http_archive(
        name = "concurrent",
        url = "https://codeload.github.com/agronholm/pythonfutures/tar.gz/3.0.5",
        sha256 = "a7086ddf3c36203da7816f7e903ce43d042831f41a9705bc6b4206c574fcb765",
        strip_prefix = "pythonfutures-3.0.5/concurrent/",
        type = "tar.gz",
        build_file_content = """
py_library(
   name = "concurrent",
   srcs = glob(["**/*.py"]),
   visibility = ["//visibility:public"]
)""",
    )

    # For packaging python tools.
    git_repository(
        name = "subpar",
        remote = "https://github.com/google/subpar",
        commit = "0356bef3fbbabec5f0e196ecfacdeb6db62d48c0",  # 2019-03-07
    )
