#!/usr/bin/env bash
# The PACS on S3: a read-only connection, then the header-index view. Needs the read-only key (HC_S3_KEY_FILE,
# created by setup/s3_reader.sh) and the images uploaded by `data/imaging.py upload`.
source "$(dirname "$0")/common.sh"
KEY="$S3_KEY_FILE"
[[ -s "$KEY" ]] || die "no $KEY yet: run setup/s3_reader.sh first"
[[ "$S3_BUCKET" != your-bucket-name ]] || die "set HC_S3_BUCKET in config.env"
AK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['AccessKey']['AccessKeyId'])" "$KEY")
SK=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['AccessKey']['SecretAccessKey'])" "$KEY")

say "1. Read-only S3 connection (GetObject + ListBucket on one bucket)"
# the secret goes into a mode-600 file that is deleted at once, so it never appears in a process listing or in the output
printf "CREATE OR REPLACE CONNECTION HOSP_S3 TO 'https://%s.s3.%s.amazonaws.com' USER '%s' IDENTIFIED BY '%s';\n" \
  "$S3_BUCKET" "$S3_REGION" "$AK" "$SK" > "$WORK/.s3conn.sql"
chmod 600 "$WORK/.s3conn.sql"; xfile "$WORK/.s3conn.sql"; rm -f "$WORK/.s3conn.sql"
ok "HOSP_S3"

say "2. Imaging views, read in place"
sed "s|{{S3_PREFIX}}|$S3_PREFIX|g" "$ROOT/sql/25_imaging.sql" > "$WORK/25_imaging.sql"
xfile "$WORK/25_imaging.sql"
xsql "SELECT MODALITY, COUNT(*) AS STUDIES FROM HOSP_CORE.IMAGING_STUDIES GROUP BY MODALITY ORDER BY 1;"
