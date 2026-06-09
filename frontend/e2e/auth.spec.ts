/**
 * 认证链路 E2E 测试。
 * 
 * 覆盖登录、登出、Token 刷新等核心场景。
 */
import { test, expect } from '@playwright/test';

// 测试账号配置
const TEST_USER = {
  email: process.env.E2E_TEST_EMAIL || 'test@example.com',
  password: process.env.E2E_TEST_PASSWORD || 'test123456',
};

test.describe('认证流程', () => {
  test.beforeEach(async ({ page }) => {
    // 清除存储状态
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
  });

  test('登录页面可访问', async ({ page }) => {
    await page.goto('/login');
    
    // 验证登录表单元素存在
    await expect(page.locator('input[type="email"], input[placeholder*="邮箱"], input[placeholder*="用户名"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"], button:has-text("登录")')).toBeVisible();
  });

  test('空表单提交显示错误', async ({ page }) => {
    await page.goto('/login');
    
    // 直接点击登录按钮
    await page.click('button[type="submit"], button:has-text("登录")');
    
    // 验证有错误提示
    await expect(page.locator('.el-form-item__error, .error-message, [role="alert"]')).toBeVisible();
  });

  test('错误密码显示提示', async ({ page }) => {
    await page.goto('/login');
    
    // 填写错误的凭据
    await page.fill('input[type="email"], input[placeholder*="邮箱"], input[placeholder*="用户名"]', 'wrong@example.com');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"], button:has-text("登录")');
    
    // 等待错误提示
    await expect(page.locator('.el-message--error, .el-notification--error, [role="alert"]')).toBeVisible({ timeout: 10000 });
  });

  test('成功登录跳转到首页', async ({ page }) => {
    // 跳过如果没有测试账号
    test.skip(!process.env.E2E_TEST_EMAIL, '需要配置 E2E_TEST_EMAIL 环境变量');
    
    await page.goto('/login');
    
    // 填写正确的凭据
    await page.fill('input[type="email"], input[placeholder*="邮箱"], input[placeholder*="用户名"]', TEST_USER.email);
    await page.fill('input[type="password"]', TEST_USER.password);
    await page.click('button[type="submit"], button:has-text("登录")');
    
    // 等待跳转
    await page.waitForURL('**/', { timeout: 10000 });
    
    // 验证已登录状态
    await expect(page.locator('[data-testid="user-menu"], .user-avatar, .user-dropdown')).toBeVisible();
  });

  test('未登录访问受保护页面跳转到登录', async ({ page }) => {
    // 直接访问需要登录的页面
    await page.goto('/knowledge');
    
    // 应该跳转到登录页
    await expect(page).toHaveURL(/\/login/);
  });

  test('登出后跳转到登录页', async ({ page }) => {
    test.skip(!process.env.E2E_TEST_EMAIL, '需要配置 E2E_TEST_EMAIL 环境变量');
    
    // 先登录
    await page.goto('/login');
    await page.fill('input[type="email"], input[placeholder*="邮箱"], input[placeholder*="用户名"]', TEST_USER.email);
    await page.fill('input[type="password"]', TEST_USER.password);
    await page.click('button[type="submit"], button:has-text("登录")');
    await page.waitForURL('**/', { timeout: 10000 });
    
    // 点击登出
    await page.click('[data-testid="user-menu"], .user-avatar, .user-dropdown');
    await page.click('text=退出, text=登出, text=退出登录');
    
    // 验证跳转到登录页
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('注册流程', () => {
  test('注册页面可访问', async ({ page }) => {
    await page.goto('/register');
    
    // 验证注册表单元素存在
    await expect(page.locator('input[placeholder*="邮箱"]')).toBeVisible();
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
  });

  test('注册表单验证', async ({ page }) => {
    await page.goto('/register');
    
    // 填写无效邮箱
    await page.fill('input[placeholder*="邮箱"]', 'invalid-email');
    await page.click('button[type="submit"], button:has-text("注册")');
    
    // 验证有错误提示
    await expect(page.locator('.el-form-item__error, .error-message')).toBeVisible();
  });
});
