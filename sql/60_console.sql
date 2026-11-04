-- HOSP_CONSOLE: what the dash-server console needs beyond the HOSP_CORE views. The console runs as the kit's read-only
-- user (MCP_READONLY), which cannot read the DBA audit tables, so the audit log is exposed through a view owned by the
-- admin: only the two named demo users' SELECTs, nothing else in the audit log.
CREATE SCHEMA IF NOT EXISTS HOSP_CONSOLE;
CREATE OR REPLACE VIEW HOSP_CONSOLE.AGENT_AUDIT AS
SELECT s.USER_NAME, a.START_TIME, a.SUCCESS, ROUND(a.DURATION, 2) AS SECS, SUBSTR(a.SQL_TEXT, 1, 70) AS SQL_TEXT
FROM   EXA_DBA_AUDIT_SQL a
JOIN   EXA_DBA_AUDIT_SESSIONS s ON s.SESSION_ID = a.SESSION_ID
WHERE  s.USER_NAME IN ('HOSP_DR_BRB', 'HOSP_QUALITY_ANALYST') AND a.COMMAND_NAME = 'SELECT'
  AND  a.SQL_TEXT NOT LIKE '/*snapshot execution*/%';
GRANT SELECT ON SCHEMA HOSP_CONSOLE TO MCP_READONLY;
