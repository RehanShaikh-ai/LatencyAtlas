-- ======================================================
-- Script: 04_sla_compliance_views.sql
--
-- Objectives:
--     Define buckets on the basis of SLA thresholds.
--     Define a column for severity of the delay.
--     Use config CTE to enable a configurable approach to modify SLA buckets and 
--     severity upon change in SLA threshold.
--   
-- NOTE:
--     This layer is built upon v_sla_base.
--     The SLA buckets and severity are both derived solely through resolution_minutes.
--
-- Output:
--      v_sla with derived columns buckets and severity.
--   
-- ======================================================

CREATE OR REPLACE VIEW
v_sla
AS
WITH sla_config AS (
    SELECT 
        3 * 24 * 60 AS excellent_limit,
        7 * 24 * 60 AS compliant_limit,
        14 * 24 * 60 AS breach_limit
)
SELECT
b.*,

CASE 
    WHEN resolution_minutes <= conf.excellent_limit
    THEN '0-3 days'

    WHEN resolution_minutes <= conf.compliant_limit
    THEN '4-7 days'

    WHEN resolution_minutes <= conf.breach_limit
    THEN '8-14 days'

    ELSE '>14 days'
END AS bucket,


CASE 
    WHEN resolution_minutes <= conf.excellent_limit
    THEN 'Excellent'

    WHEN resolution_minutes <= conf.compliant_limit
    THEN 'Compliant'

    WHEN resolution_minutes <= conf.breach_limit
    THEN 'Breach'

    ELSE 'Extreme Breach'

END AS severity 
FROM v_sla_base b
CROSS JOIN sla_config conf;


