export CUDA_VISIBLE_DEVICES=2
python run.py \
    --problem cvrp \
    --N_aug 2 \
    --graph_size 20 \
    --log_name sym-nco-am-cvrp20 &

sleep 5

export CUDA_VISIBLE_DEVICES=4
python run.py \
    --problem cvrp \
    --N_aug 2 \
    --graph_size 20 \
    --supervise_lambda 0.1 \
    --num_equivariant_samples 5 \
    --log_name sym-nco-am-eq5-lambda0.1-cvrp20 &