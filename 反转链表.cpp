/*链表反转*/
#include <iostream>

using namespace std;

struct node {
    int data;
    node* next;
};

void insertNode(node* head, int value) {
    node* p = head;
    while (p->next) {
        p = p->next;
    }
    p->next = new node{value, nullptr};
}

void reverseList(node* head) {
    node* cur = head->next;
    if (cur == nullptr) {
        return;
    }

    node* pre = nullptr;
    while (cur) {
        node* next = cur->next;
        cur->next = pre;
        pre = cur;
        cur = next;
    }

    head->next = pre;
}

int main() {
    node* list = new node{-1, nullptr};

    int value;
    while (cin >> value) {
        insertNode(list, value);
    }

    reverseList(list);

    for (node* p = list->next; p; p = p->next) {
        cout << p->data;
    }

    cout << '\n';

    while (list) {
        node* next = list->next;
        delete list;
        list = next;
    }

    return 0;
}
