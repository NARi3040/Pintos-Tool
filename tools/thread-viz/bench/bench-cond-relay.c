/* thread-viz 벤치 (공식 테스트 아님, make check에 안 들어감).
   priority가 제각각인 스레드 8개가 condition variable에서 기다리고, 가장 낮은 main이 한 번에 하나씩 깨움.
   깨어난 스레드는 main이 쥔 락이 필요해서 donation을 거쳐 main을 선점함. 이걸 여러 라운드 반복함
   (cond_signal / sema_up이 고르는 순서, donation 후 선점).
   테스트 자체 검사: 라운드마다 priority가 높은 순서대로 깨어나야 함. */

#include <stdint.h>
#include <stdio.h>
#include "tests/threads/tests.h"
#include "threads/init.h"
#include "threads/synch.h"
#include "threads/thread.h"

#define N 8
#define ROUNDS 3

static struct lock lock;
static struct condition cond;
static struct semaphore next_round, done;
static int order[ROUNDS][N];   /* 라운드별로 깨어난 순서대로 priority를 적음 (lock으로 보호) */
static int count[ROUNDS];
static int cur_round;
static thread_func relay_thread;

void
test_bench_cond_relay (void)
{
  int i, r;

  ASSERT (!thread_mlfqs);

  lock_init (&lock);
  cond_init (&cond);
  sema_init (&next_round, 0);
  sema_init (&done, 0);

  thread_set_priority (PRI_MAX);
  for (i = 0; i < N; i++)
    {
      int priority = PRI_MIN + 10 + (i * 3) % N * 6;   /* 3과 N은 서로소 */
      char name[16];
      snprintf (name, sizeof name, "relay %d", priority);
      thread_create (name, priority, relay_thread, (void *) (intptr_t) priority);
    }
  /* 낮추는 순간 모두 실행돼서 cond에서 기다리게 됨 */
  thread_set_priority (PRI_MIN);

  for (r = 0; r < ROUNDS; r++)
    {
      cur_round = r;
      for (i = 0; i < N; i++)
        {
          lock_acquire (&lock);
          cond_signal (&cond, &lock);
          lock_release (&lock);
        }
      /* 이번 라운드를 끝낸 스레드들을 다음 라운드의 cond 대기로 돌려보냄 */
      for (i = 0; i < N; i++)
        sema_up (&next_round);
    }
  for (i = 0; i < N; i++)
    sema_down (&done);

  for (r = 0; r < ROUNDS; r++)
    for (i = 1; i < N; i++)
      if (order[r][i] > order[r][i - 1])
        fail ("%d라운드: priority %d가 %d보다 먼저 깨어남", r + 1,
              order[r][i - 1], order[r][i]);
}

static void
relay_thread (void *aux)
{
  int priority = (intptr_t) aux;
  int r;

  for (r = 0; r < ROUNDS; r++)
    {
      lock_acquire (&lock);
      cond_wait (&cond, &lock);
      order[cur_round][count[cur_round]++] = priority;
      lock_release (&lock);
      if (r + 1 < ROUNDS)
        sema_down (&next_round);
    }
  sema_up (&done);
}
