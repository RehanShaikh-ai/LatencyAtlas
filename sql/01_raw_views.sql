
-- ======================================================
-- Script: 01_raw_views.sql
--
-- Objective:
--
-- Store the raw NYC 311 parquet data without any filtering
-- Preserve the unadulterated data after API ingestion
-- 
-- Source: 
-- data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9/about_data
--
-- ======================================================



CREATE OR REPLACE VIEW v_raw AS SELECT 

unique_key, 
created_date, 
closed_date, 
agency, 
agency_name, 
complaint_type, 
descriptor, 
status, 
borough 

FROM read_parquet(getvariable('data_root') ||'/NYC311.parquet');
