# Copyright 2020 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#
# This software is provided as-is,
# without warranty or representation for any use or purpose.
# Your use of it is subject to your agreement with Google.

data "template_file" "rendered_script" {
  template = file(var.tmpl_file)
  vars = merge(
    var.subs,
    {
      logic = file(var.logic_file == "" ? join("", [trimsuffix(var.tmpl_file, var.tmpl_suffix), var.logic_suffix]) : var.logic_file)
  })
}
