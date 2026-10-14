/* thread-viz 벤치 (공식 테스트 아님, make check에 안 들어감).
   리스트 길이를 0에서 N까지 키우고 줄이면서 동기화·타이머 함수의 비용이 길이에 따라 늘어나는지 재는 테스트.
   thread-viz가 호출마다 (리스트 길이, 명령어 수)를 모아서 상수 / 선형 / 선형 초과로 판정함.
   1) sleep_list: N개 스레드가 tick 하나씩 간격으로 깨어나서 timer_interrupt가 볼 때 sleep_list가 N -> 0으로 줄어듦
   2) lock: main이 쥔 락에 N개 스레드가 줄을 서고 하나씩 넘겨받음 (lock_acquire/lock_release/sema_*)
   3) condition: N개 스레드가 cond_wait로 줄을 서고 main이 cond_signal로 하나씩 깨움
   테스트 자체 검사: 일찍 깨어난 스레드가 없고 모든 스레드가 끝까지 실행돼야 함. */

#include <stdint.h>
#include <stdio.h>
#include "tests/threads/tests.h"
#include "threads/init.h"
#include "threads/interrupt.h"
#include "threads/synch.h"
#include "threads/thread.h"
#include "devices/timer.h"

#define N 48

static int64_t start;
static int finished;   /* 단계마다 끝낸 스레드 수 */
static int early;      /* 목표 tick보다 일찍 깨어난 스레드 수 */
static struct lock lock;
static struct condition cond;
static thread_func sleep_thread, lock_thread, cond_thread;

static void
done (void)
{
  enum intr_level old_level = intr_disable ();
  finished++;
  intr_set_level (old_level);
}

static void
wait_all (void)
{
  while (finished < N)
    barrier ();
  finished = 0;
}

void
test_bench_scale (void)
{
  int i;

  ASSERT (!thread_mlfqs);

  /* 1) 깨어나는 tick이 하나씩 다름. 먼저 깨는 쪽이 priority가 낮도록 해서 priority 순서와 tick 순서가 섞이게 함 */
  thread_set_priority (PRI_MIN);
  start = timer_ticks () + 10;
  for (i = 0; i < N; i++)
    thread_create ("sleep", PRI_MIN + 1 + (i * 7) % N, sleep_thread, (void *) (intptr_t) i);
  wait_all ();
  if (early)
    fail ("%d개 스레드가 목표 tick보다 일찍 깨어남", early);

  /* 2) 락: main이 최고 priority로 락을 쥐고 스레드를 만들면 다들 main보다 낮아서 아직 안 돎.
     main이 잠들면 스레드들이 차례로 락에 줄을 섬 (줄이 0에서 N까지 길어짐) */
  lock_init (&lock);
  thread_set_priority (PRI_MAX);
  lock_acquire (&lock);
  for (i = 0; i < N; i++)
    thread_create ("lock", PRI_MIN + 1 + (i * 7) % N, lock_thread, NULL);
  timer_sleep (2);
  lock_release (&lock);
  thread_set_priority (PRI_MIN);   /* 넘겨받은 스레드들이 차례로 돌며 줄이 N에서 0으로 줄어듦 */
  wait_all ();

  /* 3) condition: 같은 방식으로 줄을 세우고 main이 하나씩 깨움 */
  cond_init (&cond);
  thread_set_priority (PRI_MAX);
  for (i = 0; i < N; i++)
    thread_create ("cond", PRI_MIN + 1 + (i * 7) % N, cond_thread, NULL);
  timer_sleep (2);
  for (i = 0; i < N; i++)
    {
      lock_acquire (&lock);
      cond_signal (&cond, &lock);
      lock_release (&lock);
    }
  thread_set_priority (PRI_MIN);
  wait_all ();
}

static void
sleep_thread (void *aux)
{
  int64_t target = start + (intptr_t) aux;

  timer_sleep (target - timer_ticks ());
  if (timer_ticks () < target)
    early++;
  done ();
}

static void
lock_thread (void *aux UNUSED)
{
  lock_acquire (&lock);
  lock_release (&lock);
  done ();
}

static void
cond_thread (void *aux UNUSED)
{
  lock_acquire (&lock);
  cond_wait (&cond, &lock);
  lock_release (&lock);
  done ();
}
