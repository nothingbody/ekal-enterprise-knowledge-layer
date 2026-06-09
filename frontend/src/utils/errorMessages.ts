/**
 * 错误消息映射工具。
 * 
 * 将后端错误码转换为用户友好的提示信息。
 */

export interface ErrorAction {
  text: string
  route?: string
  handler?: () => void
}

export interface ErrorMessage {
  title: string
  description: string
  action: ErrorAction | null
}

/**
 * 错误码到消息的映射表。
 */
export const ERROR_MESSAGES: Record<string, ErrorMessage> = {
  // 模型相关
  model_not_configured: {
    title: '未配置 AI 模型',
    description: '请先配置至少一个 AI 模型才能开始对话',
    action: { text: '配置模型', route: '/models' },
  },
  model_not_found: {
    title: '模型不存在',
    description: '所选模型已被删除或不可用，请重新选择',
    action: { text: '选择模型', route: '/models' },
  },
  api_key_invalid: {
    title: 'API Key 无效',
    description: '请检查 API Key 是否正确，或联系模型服务商获取新的 Key',
    action: { text: '重新配置', route: '/models' },
  },
  api_key_expired: {
    title: 'API Key 已过期',
    description: '您的 API Key 已过期，请更新',
    action: { text: '更新配置', route: '/models' },
  },

  // 知识库相关
  knowledge_base_empty: {
    title: '知识库为空',
    description: '请先上传文档到知识库',
    action: { text: '上传文档', route: '/knowledge' },
  },
  knowledge_base_not_found: {
    title: '知识库不存在',
    description: '所选知识库已被删除，请重新选择',
    action: { text: '选择知识库', route: '/knowledge' },
  },
  document_processing: {
    title: '文档正在处理中',
    description: '请等待文档处理完成后再进行对话',
    action: null,
  },

  // 配额相关
  rate_limit_exceeded: {
    title: '请求过于频繁',
    description: '请稍后再试',
    action: null,
  },
  quota_exceeded: {
    title: '配额已用完',
    description: '您的对话配额已用完，请联系管理员或升级套餐',
    action: null,
  },
  trial_expired: {
    title: '试用已结束',
    description: '您的免费试用已结束，请升级到付费版本',
    action: null,
  },

  // 认证相关
  token_expired: {
    title: '登录已过期',
    description: '请重新登录',
    action: { text: '重新登录', route: '/login' },
  },
  unauthorized: {
    title: '未授权',
    description: '您没有权限执行此操作',
    action: null,
  },
  forbidden: {
    title: '访问被拒绝',
    description: '您没有权限访问此资源',
    action: null,
  },

  // 网络相关
  network_error: {
    title: '网络连接失败',
    description: '请检查网络连接后重试',
    action: null,
  },
  timeout: {
    title: '请求超时',
    description: '服务器响应超时，请稍后重试',
    action: null,
  },
  server_error: {
    title: '服务器错误',
    description: '服务器内部错误，请稍后重试或联系管理员',
    action: null,
  },

  // 数据库相关
  database_connection_error: {
    title: '数据库连接失败',
    description: '无法连接到数据库，请检查数据库配置',
    action: null,
  },
  sql_execution_error: {
    title: 'SQL 执行失败',
    description: '数据库查询执行失败，请检查数据库配置或联系管理员',
    action: null,
  },

  // 文件相关
  file_too_large: {
    title: '文件过大',
    description: '上传的文件超过大小限制',
    action: null,
  },
  file_type_not_supported: {
    title: '文件类型不支持',
    description: '请上传 PDF、Word、Excel、PPT、Markdown、TXT 等格式的文件',
    action: null,
  },
  file_parse_error: {
    title: '文件解析失败',
    description: '无法解析文件内容，请检查文件是否损坏',
    action: null,
  },

  // 向量存储相关
  vector_store_error: {
    title: '向量存储错误',
    description: '向量数据库操作失败，请联系管理员',
    action: null,
  },
  embedding_error: {
    title: '向量化失败',
    description: '文档向量化处理失败，请检查 Embedding 模型配置',
    action: { text: '检查配置', route: '/models' },
  },
}

/**
 * 根据错误码获取用户友好的错误消息。
 */
export function getErrorMessage(code: string): ErrorMessage {
  // 尝试精确匹配
  if (ERROR_MESSAGES[code]) {
    return ERROR_MESSAGES[code]
  }

  // 尝试模糊匹配
  const lowerCode = code.toLowerCase()
  for (const [key, value] of Object.entries(ERROR_MESSAGES)) {
    if (lowerCode.includes(key) || key.includes(lowerCode)) {
      return value
    }
  }

  // 默认消息
  return {
    title: '操作失败',
    description: code || '未知错误',
    action: null,
  }
}

/**
 * 从 HTTP 状态码获取错误消息。
 */
export function getErrorFromStatus(status: number, detail?: string): ErrorMessage {
  switch (status) {
    case 400:
      return getErrorMessage(detail || 'bad_request')
    case 401:
      return getErrorMessage('token_expired')
    case 403:
      return getErrorMessage('forbidden')
    case 404:
      return {
        title: '资源不存在',
        description: detail || '请求的资源不存在',
        action: null,
      }
    case 422:
      return {
        title: '参数错误',
        description: detail || '请求参数不正确',
        action: null,
      }
    case 429:
      return getErrorMessage('rate_limit_exceeded')
    case 500:
      return getErrorMessage('server_error')
    case 502:
    case 503:
    case 504:
      return {
        title: '服务暂时不可用',
        description: '服务器正在维护或过载，请稍后重试',
        action: null,
      }
    default:
      return getErrorMessage(detail || 'unknown_error')
  }
}

/**
 * 解析 API 响应错误。
 */
export function parseApiError(error: any): ErrorMessage {
  // Axios 错误
  if (error?.response) {
    const { status, data } = error.response
    const detail = data?.detail || data?.message || data?.error
    return getErrorFromStatus(status, detail)
  }

  // 网络错误
  if (error?.code === 'ECONNABORTED' || error?.message?.includes('timeout')) {
    return getErrorMessage('timeout')
  }
  if (error?.code === 'ERR_NETWORK' || error?.message?.includes('Network Error')) {
    return getErrorMessage('network_error')
  }

  // 其他错误
  return getErrorMessage(error?.message || String(error))
}
