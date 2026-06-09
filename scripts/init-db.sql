-- 知枢 RAG 平台数据库初始化脚本
-- 为 Backend 和 Server 创建独立数据库
-- rag_platform (backend 使用) 由 POSTGRES_DB 环境变量自动创建
-- rag_central (server 使用) 在此处创建

CREATE DATABASE rag_central OWNER rag;
