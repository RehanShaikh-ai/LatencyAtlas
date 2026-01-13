-- ======================================================
-- Script: 03_sla_base.sql
--
-- Objectives:
--     Calculate the time difference between the creation and closure of requests
--     Filter the data to operate only on closed requests 
--     Enable granularity by calculating the difference in Minutes instead of Days or Hours
--  
-- NOTE:
--     This layer is built upon v_norm layer.
--     The resolution_minutes is calculaed solely on closed requests, filtering out 
--     requests with Open and Unspecified status.
--     For filtering, the derived column normalized_status is used not status column.   
--  
-- Output: 
--      v_sla_base with derived column resolution_minutes.  
--
-- ======================================================

CREATE OR REPLACE VIEW 
v_sla_base
AS 
SELECT 
*,
DATEDIFF('MINUTE', created_ts, closed_ts) AS resolution_minutes
FROM v_norm 
WHERE normalized_status = 'Closed'
AND closed_ts IS NOT NULL;

g
