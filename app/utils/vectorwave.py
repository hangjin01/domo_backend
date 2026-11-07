# [파일 안내] backend/app/utils/vectorwave.py
# 선택 의존성 VectorWave의 vectorize 데코레이터를 제공하는 호환 경계입니다.
# 라이브러리가 없으면 원래 함수를 그대로 반환해 기본 로컬 API를 실행할 수 있게 합니다. 이 경우 AI 벡터화/추적이 수행되는 것은 아닙니다.

"""Optional VectorWave integration.

The collaboration APIs work without the AI indexing service.  Keeping a
no-op decorator here makes a local development server independent of the
large VectorWave/Torch dependency stack.
"""

try:
    from vectorwave import vectorize as _vectorize
except ImportError:
    def vectorize(**_options):
        def decorator(function):
            return function
        return decorator
else:
    vectorize = _vectorize
