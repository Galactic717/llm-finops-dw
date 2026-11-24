select coalesce(s.event_id, f.event_id) as event_id
from {{ ref('stg_llm_runs') }} as s
full outer join {{ ref('fct_llm_runs') }} as f using (event_id)
where s.event_id is null or f.event_id is null
