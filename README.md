# PitWall deploy data

`pitwall-data.tar.gz` is the data a hosted PitWall needs (database, lap files, backtest
results), built by `scripts/pack_data.py` on `main`. `Dockerfile.render` downloads it at build
time. This branch is replaced (force-pushed) on every data update, so it holds one commit.
