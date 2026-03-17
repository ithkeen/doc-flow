CREATE TABLE t_api_index (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    api    VARCHAR(128) NOT NULL COMMENT 'API函数名',
    project     VARCHAR(128) NOT NULL COMMENT '项目名',
    source      VARCHAR(512) NOT NULL COMMENT '源码路径（相对于codespace根目录）',
    doc         VARCHAR(512) NOT NULL COMMENT '文档路径（相对于docspace根目录）',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_api_project (api, project) COMMENT '同一项目下函数名唯一'
) COMMENT = 'API文档索引表';