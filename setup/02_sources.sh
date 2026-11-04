#!/usr/bin/env bash
# Attach the two branch systems to Exasol as virtual schemas. Nothing is copied.
#   HOSP_LEGACY        Branch A/Branch C legacy HIS on Postgres  (official PostgreSQL virtual schema, JDBC)
#   HOSP_EHR_PATIENTS  modern EHR patients on MongoDB            (exasol-labs MongoDB virtual schema)
#   HOSP_EHR_ENCOUNTERS modern EHR encounters on MongoDB
# Connections use READ-ONLY logins on each source. Idempotent.
source "$(dirname "$0")/common.sh"

say "1. JDBC adapter + driver into BucketFS"
mkdir -p "$BFS/default/hospital/jars"
VS_JAR=virtual-schema-dist-14.0.4-postgresql-4.0.1.jar; PG_JAR=postgresql-42.7.4.jar
[[ -s "$WORK/$VS_JAR" ]] || curl -fsSL -o "$WORK/$VS_JAR" "https://github.com/exasol/postgresql-virtual-schema/releases/download/4.0.1/$VS_JAR"
[[ -s "$WORK/$PG_JAR" ]] || curl -fsSL -o "$WORK/$PG_JAR" "https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/$PG_JAR"
cp "$WORK/$VS_JAR" "$WORK/$PG_JAR" "$BFS/default/hospital/jars/"
sleep 3; ok "$(ls "$BFS/default/hospital/jars" | tr '\n' ' ')"

# holds the read-only logins' passwords: written mode 600 and removed once run
(umask 077; cat > "$WORK/02_sources.sql") <<SQL
CREATE SCHEMA IF NOT EXISTS HOSP_ADAPTERS;
CREATE OR REPLACE JAVA ADAPTER SCRIPT HOSP_ADAPTERS.POSTGRES_ADAPTER AS
  %scriptclass com.exasol.adapter.RequestDispatcher;
  %jvmoption -Duser.timezone=UTC;
  %jar /buckets/bfsdefault/default/hospital/jars/virtual-schema-dist-14.0.4-postgresql-4.0.1.jar;
  %jar /buckets/bfsdefault/default/hospital/jars/postgresql-42.7.4.jar;
/
CREATE OR REPLACE CONNECTION HOSP_LEGACY_PG TO 'jdbc:postgresql://$SRC_HOST:$PG_PORT/branch_a_his'
  USER 'his_reader' IDENTIFIED BY '$HC_PG_READER_PASSWORD';
CREATE OR REPLACE CONNECTION HOSP_MODERN_MONGO TO 'mongodb://$SRC_HOST:$MONGO_PORT/?authSource=admin&directConnection=true'
  USER 'ehr_reader' IDENTIFIED BY '$HC_MONGO_READER_PASSWORD';
DROP VIRTUAL SCHEMA IF EXISTS HOSP_LEGACY CASCADE;
CREATE VIRTUAL SCHEMA HOSP_LEGACY USING HOSP_ADAPTERS.POSTGRES_ADAPTER WITH
  CONNECTION_NAME = 'HOSP_LEGACY_PG' CATALOG_NAME = 'branch_a_his' SCHEMA_NAME = 'his'
  POSTGRESQL_IDENTIFIER_MAPPING = 'CONVERT_TO_UPPER';
DROP VIRTUAL SCHEMA IF EXISTS HOSP_EHR_PATIENTS CASCADE;
CREATE VIRTUAL SCHEMA HOSP_EHR_PATIENTS USING MONGODB_VS.MONGODB_ADAPTER WITH
  MONGODB_CONNECTION = 'HOSP_MODERN_MONGO' DATABASE = 'ehr' COLLECTION = 'patients' INFERENCE_SAMPLE_SIZE = '2000';
DROP VIRTUAL SCHEMA IF EXISTS HOSP_EHR_ENCOUNTERS CASCADE;
CREATE VIRTUAL SCHEMA HOSP_EHR_ENCOUNTERS USING MONGODB_VS.MONGODB_ADAPTER WITH
  MONGODB_CONNECTION = 'HOSP_MODERN_MONGO' DATABASE = 'ehr' COLLECTION = 'encounters' INFERENCE_SAMPLE_SIZE = '3000';
SQL

say "2. Connections + virtual schemas"
xfile "$WORK/02_sources.sql" || { rm -f "$WORK/02_sources.sql"; die "connections / virtual schemas failed"; }
rm -f "$WORK/02_sources.sql"
xsql "SELECT COLUMN_SCHEMA, COLUMN_TABLE, COUNT(*) AS COLS FROM EXA_ALL_COLUMNS
      WHERE COLUMN_SCHEMA IN ('HOSP_LEGACY','HOSP_EHR_PATIENTS','HOSP_EHR_ENCOUNTERS') GROUP BY 1,2 ORDER BY 1,2;"

say "3. Register the driver for Exasol's loader (pushdown runs as IMPORT FROM JDBC)"
# NOT BucketFS drivers/jdbc as the docs say: this Personal build's loader reads etlJdbcConfigDir=$EXADIR/jdbc
# (exasol.conf), which is the VM-shared exa/jdbc directory on the Mac. Found in the SqlSession log.
JDBC_DIR="$DEPLOY_DIR/local/runtime/vm-shared/exa/jdbc/postgresql"
mkdir -p "$JDBC_DIR"
cmp -s "$WORK/$PG_JAR" "$JDBC_DIR/$PG_JAR" || cp "$WORK/$PG_JAR" "$JDBC_DIR/"
# NOSECURITY=YES lets the loader run this driver without Java's security manager, which the PostgreSQL JDBC driver
# needs on Exasol. Acceptable on a single-user local Exasol Personal; review it before doing the same on a shared cluster.
printf 'DRIVERNAME=POSTGRESQL\nJAR=postgresql-42.7.4.jar\nDRIVERMAIN=org.postgresql.Driver\nPREFIX=jdbc:postgresql:\nFETCHSIZE=100000\nINSERTSIZE=-1\nNOSECURITY=YES\n\n' > "$JDBC_DIR/settings.cfg"
sleep 4
xsql "SELECT COUNT(*) AS LEGACY_PATIENTS FROM HOSP_LEGACY.PAT_MSTR;"
