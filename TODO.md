* share pieces that aren't checked in across worktrees
  * claude settings (to share setup and avoid the permissions init screen)
  * .terraform directories
  * .env files
  * .localdev
  * direnv
  * bazel cache/state/etc.

* rework 'ss' command to do the right thing/stop actually 'cd'ing to a specific
  directory.
  * does 'wt pwd' solve the 'go to' part of this?
  * beyond that, just need to source the common `.localdev/rc` file

* put `wt` on PATH and set WT_CONFIG in rc file etc.
*
