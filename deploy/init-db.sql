-- 初始化脚本：在同一个 PostgreSQL 实例中创建两个数据库
-- rag_platform (backend 使用) 由 POSTGRES_DB 环境变量自动创建
-- rag_central (server 使用) 在此处创建

CREATE DATABASE rag_central OWNER rag;
