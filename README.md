# Build docker image locally & Start i2b2-etl
clone the i2b2-etl & Mozilla repo 

git clone https://github.com/i2b2/i2b2-etl.git 

git clone https://github.com/i2b2/i2b2-cdi-qs-mozilla.git

## Copy Mozilla folder inside i2b2-etl repo
cp -r  mozilla-i2b2-etl/Mozilla/  i2b2-etl/

cd i2b2-etl

## Build the docker image locally 
docker build -t i2b2/i2b2-etl:local-v1 . 

## Update the etl tag & start i2b2-etl container
open i2b2-etl-docker/postgres/.env file 

update i2b2-etl tag to local-v1

## Remove the existing i2b2-etl docker container 
docker rm -f i2b2-etl

## Start the new i2b2-etl container 
docker-compose up -d i2b2-etl 

## To execute the test cases

Start a bash shell inside the i2b2-etl container
```shell
$ docker exec -it i2b2-etl bash
python -m unittest discover -s i2b2_cdi/test/
```

# i2b2-etl
i2b2-etl provides a command line interface and api interface to import, delete concepts and facts and encounters.

## Deploy i2b2 with etl container
refer to i2b2-docker project repo to deploy i2b2 with etl container

## Executing the I2B2-ETL 

```shell
Start a bash shell inside the i2b2-etl container
$ docker exec -it i2b2-etl bash

For ease of documentation use etl as an alias for command invocation
$ alias etl="python -m i2b2_cdi ${ARGS}"
```
### I2B2-ETL commands
Below commands helps to play with I2B2-ETL

### Help
This will list all possible operation of i2b2-etl
```shell
$ etl --help
OR
$ etl -h
```

### Delete concepts
```shell
$ etl concept delete -c <env-file>
```

### Load concepts
```shell
$ etl concept load -c <env-file> -i <input-dir>
```

> **_Note:_** File name should have pattern like *_concepts.csv

### Delete facts
```shell
$ etl fact delete -c <env-file>
```

### Load facts
Load facts with concept_cd validation.
```shell
$ etl fact load -c <env-file> -i <input-dir>
```
Load facts with no concept_cd validation.
```shell
$ etl fact load -c <env-file> -i <input-dir> --disable-fact-validation
```
> **_Note:_** File name should have pattern like *_facts.csv



### Delete patients
```shell
$ etl patient delete -c <env-file>
```

### Load patients
```shell
$ etl patient load -c <env-file> -i <input-dir>
```

### Delete encounters
```shell
$ etl encounter delete -c <env-file>
```

### Load encounters
```shell
$ etl encounter load -c <env-file> -i <input-dir>
```

### Create project and user
Create new project & user along with password , also assign new project to new user.
```shell
$ etl project add -c <config-file> --project-name <project-name> --project-user-password <project-user-password>
```

### Load data into project
Copy data from one project to another.
```shell
$ etl project load -c <config-file> --project-name <project-name> 
```
### Change user password
Change password for user in i2b2
```shell
$ etl project password -c <config-file> --user <user-id> --password <password>
```

##  LLM module — verification receipt

The LLM integration (see [CHANGES.md](CHANGES.md)) has been verified end-to-end
against a real Postgres + jobWatcher stack.

### Verified On

| Date | OS | Docker | Python | Tests |
|---|---|---|---|---|
| 2026-05-27 | macOS 15.6.1 (Sequoia, arm64) | 29.5.2 | 3.12.4 | 170 passed (167 unit + 3 live_pg), 0 failed, 0 skipped. Real-MIMIC pilot run completed on the Qwen-0.5B provider — see [CHANGES.md §11.6](CHANGES.md). |

## Demonstration eval harness (`evaluation/`)

The `evaluation/` directory contains the offline demonstration harness
that produces the JAMIA Open results table from a cohort CSV. See
[`evaluation/README.md`](evaluation/README.md) and [CHANGES.md §11.5](CHANGES.md).

### Verified on real MIMIC (2026-05-27)

PhysioNet DUA approved 2026-05-27. Cohort pulled via
`sql/cohort_v1.sql` (1000 rows, 7.8% HF+). Qwen-0.5B pilot ran 10
patients end-to-end (`evaluation/results/20260528T023141Z/`) — pipeline
works, retry+exhausted logic verified against real malformed JSON, all
7 output files generated. Kappa=0 is expected for Qwen-0.5B (no
clinical training); the Anthropic paper run is queued for whenever
`ANTHROPIC_API_KEY` is provisioned. See [CHANGES.md §11.6](CHANGES.md)
for the full pilot receipt.

### Running it

```bash
# Pull cohort (one-time after DUA approval)
bq query --use_legacy_sql=false < sql/cohort_v1.sql > ~/mimic_data/cohort_v1.csv

# Run with any provider (Qwen / Llama / Anthropic / OpenAI / Ollama)
PYTHONPATH=. python evaluation/run_demonstration.py \
    --cohort ~/mimic_data/cohort_v1.csv \
    --config evaluation/configs/anthropic.json    # or local_hf_qwen.json, etc.

# Inspect the latest results
python evaluation/quick_inspect.py
```

To reproduce: see [CHANGES.md §7](CHANGES.md) for the live-PG smoke procedure.

###  How to Cite
Wagholikar KB, Ainsworth L, Zelle D, et.al. I2b2-etl: Python application for importing electronic health data into the informatics for integrating biology and the bedside platform. **Bioinformatics**. 2022 Oct 14;38(20):4833-4836. 


### License

Copyright 2023 Massachusetts General Hospital.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
     http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.



