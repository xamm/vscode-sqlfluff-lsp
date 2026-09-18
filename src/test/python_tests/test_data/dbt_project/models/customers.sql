select
    customer_id,
    customer_name,
    {{ var('margin', '0.1') }} as margin
from {{ ref('stg_customers') }}
