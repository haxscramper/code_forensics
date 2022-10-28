SELECT avg((
    CASE WHEN issue.closed_at IS NULL THEN strftime('%s', 'now')
    ELSE issue.closed_at
    END
    ) - issue.created_at
  ) AS "average"
  -- ,
  -- issue.closed_at as closed,
  -- strftime('%s', 'now') as time,
  -- issue.name
  FROM issue
  WHERE NOT (issue.closed_at IS NULL)
  ;
